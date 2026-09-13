"""Deterministic orchestration. Depends exclusively on domain ports/services."""
import asyncio
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .conditions import ConditionEvaluator
from .evidence import EvidenceContext, EvidenceWriter
from .handoff_port import HandoffHandler, ResumeDisposition
from .models import Risk, ResumeInfo, Action, CapabilityArtifact, Condition, Decision, Failure, RunResult, Scalar, Status, Step
from .policy import PolicyEngine
from .resolver import LocatorResolver
from .surface import Surface, SurfaceError, SurfaceTimeout
from .templates import ValueValidationError, bind_conditions, render, validate_inputs, validate_value


class ReplayEngine:
    def __init__(self, surface: Surface, *, evidence_root: Path = Path("evidence"),
                 resolver: LocatorResolver | None = None, policy: PolicyEngine | None = None,
                 handoff: HandoffHandler | None = None,
                 evidence_context: EvidenceContext | None = None):
        self.evidence_context = evidence_context
        self.handoff = handoff
        self.surface = surface
        self.evidence_root = evidence_root
        self.resolver = resolver or LocatorResolver()
        self.policy = policy or PolicyEngine()
        self.conditions = ConditionEvaluator(self.resolver)
        self._lock = asyncio.Lock()
        self._action_attempted = False
        self._active_condition: Condition | None = None

    async def execute(self, artifact: CapabilityArtifact, inputs: Mapping[str, object]) -> RunResult:
        """Artifact parsing errors belong to loading; runtime outcomes are structured."""
        async with self._lock:
            return await self._execute(artifact, inputs)

    async def _execute(self, artifact: CapabilityArtifact, inputs: Mapping[str, object]) -> RunResult:
        run_id = uuid4().hex
        started = monotonic()
        try:
            evidence = EvidenceWriter(self.evidence_root, run_id, artifact, context=self.evidence_context)
        except OSError:
            return self._failure(run_id, None, Status.HARD_FAILURE, "EVIDENCE_UNAVAILABLE")
        current_step = None
        result = None
        typed_inputs: dict[str, Scalar] = {}
        try:
            evidence.emit("run_started", status="RUNNING")
            try:
                typed_inputs = validate_inputs(artifact.inputs, inputs)
                artifact = bind_conditions(artifact, typed_inputs)
            except ValueValidationError:
                result = self._failure(run_id, None, Status.HARD_FAILURE, "INVALID_INPUTS")
            if result is None and (
                artifact.compatibility.surface_contract != self.surface.contract_version or
                not set(artifact.compatibility.required_features) <= self.surface.features
            ):
                result = self._failure(run_id, None, Status.HARD_FAILURE, "INCOMPATIBLE_SURFACE")
            outputs: dict[str, Scalar] = {}
            if result is None:
                for step in artifact.steps:
                    current_step = step.id
                    step_started = monotonic()
                    evidence.emit("step_started", step_id=step.id, action=step.action, status="RUNNING")
                    result = await self._step(artifact, step, typed_inputs, outputs, evidence)
                    while result is not None and result.status == Status.HUMAN_REQUIRED and self.handoff:
                        disposition = await self.handoff.resolve(artifact, step, result, typed_inputs, evidence)
                        if disposition == ResumeDisposition.COMPLETED_STEP:
                            result = None
                        elif disposition == ResumeDisposition.RETRY_STEP:
                            result = await self._step(artifact, step, typed_inputs, outputs, evidence)
                        else:
                            break
                    evidence.emit("step_finished", step_id=step.id, action=step.action,
                                  duration_ms=round((monotonic() - step_started) * 1000, 3),
                                  status=result.status if result else Status.SUCCESS)
                    await evidence.screenshot(self.surface, step.id)
                    await self.surface.release_targets()
                    if result is not None:
                        break
                if result is None:
                    current_step = None
                    result = await self._checkpoint(artifact, artifact.success, evidence, None,
                                                    artifact.steps[-1].timeout_ms)
                if result is None:
                    result = RunResult(run_id=run_id, status=Status.SUCCESS, outputs=outputs)
        except (SurfaceTimeout, TimeoutError):
            result = self._failure(run_id, current_step, Status.RECOVERABLE_ERROR, "SURFACE_TIMEOUT")
        except SurfaceError:
            result = self._failure(run_id, current_step, Status.HARD_FAILURE, "SURFACE_ERROR")
        except OSError:
            result = self._failure(run_id, current_step, Status.HARD_FAILURE, "EVIDENCE_UNAVAILABLE")
        except Exception:
            # Do not serialize provider or validation exception text; it can contain secrets.
            result = self._failure(run_id, current_step, Status.HARD_FAILURE, "INTERNAL_ERROR")
        finally:
            try:
                await self.surface.release_targets()
            except Exception:
                pass
        if self.handoff:
            result = result.model_copy(update={"handoff_occurred": self.handoff.handoff_occurred,
                                               "human_action_count": self.handoff.human_action_count})
        refs = [str(evidence.directory / name) for name in ("metadata.json", "events.jsonl", "result.json")]
        result = result.model_copy(update={"evidence_refs": refs})
        if result.resume:
            result = result.model_copy(update={"resume": result.resume.model_copy(update={"evidence_ref": refs[1]})})
        if result.failure:
            result = result.model_copy(update={"failure": result.failure.model_copy(update={"evidence_refs": refs})})
        try:
            await evidence.screenshot(self.surface, None)
            evidence.emit("run_finished", status=result.status,
                          duration_ms=round((monotonic() - started) * 1000, 3))
            evidence.finish(result)
            if self.handoff:
                self.handoff.finished(result)
        except OSError:
            return self._failure(run_id, current_step, Status.HARD_FAILURE, "EVIDENCE_UNAVAILABLE")
        return result

    async def _step(self, artifact: CapabilityArtifact, step: Step,
                    inputs: Mapping[str, Scalar], outputs: dict[str, Scalar],
                    evidence: EvidenceWriter) -> RunResult | None:
        for attempt in range(1, step.retry.max_attempts + 1):
            self._action_attempted = False
            self._active_condition = None
            evidence.emit("step_attempt", step_id=step.id, action=step.action, attempt=attempt)
            try:
                # Timeout covers the entire attempt, including resolution and checkpoints.
                async with asyncio.timeout(step.timeout_ms / 1000):
                    result = await self._attempt(artifact, step, inputs, outputs, evidence)
            except (SurfaceTimeout, TimeoutError):
                result = self._failure(evidence.run_id, step.id, Status.RECOVERABLE_ERROR, "STEP_TIMEOUT",
                                       condition=self._active_condition)
            if result is not None and result.failure:
                result = result.model_copy(update={"failure": result.failure.model_copy(
                    update={"action_attempted": self._action_attempted})})
            if result is None or result.status != Status.RECOVERABLE_ERROR:
                return result
            if step.risk == Risk.IRREVERSIBLE:
                # Never replay an uncertain mutation, even if a caller labels it repeatable.
                if step.postcondition:
                    verified = await self._checkpoint(artifact, step.postcondition, evidence, step.id, step.timeout_ms)
                    if verified is None:
                        return None
                    if verified.status == Status.BUSINESS_OUTCOME:
                        return verified
                uncertain = self._failure(evidence.run_id, step.id, Status.HUMAN_REQUIRED,
                                          "UNCERTAIN_MUTATION", condition=step.postcondition)
                assert uncertain.failure is not None
                return uncertain.model_copy(update={"failure": uncertain.failure.model_copy(
                    update={"action_attempted": self._action_attempted})})
            if not step.retry.safe_to_repeat:
                assert result.failure is not None  # Recoverable failures always carry details.
                return result.model_copy(update={"failure": result.failure.model_copy(update={"retryable": False})})
            if attempt == step.retry.max_attempts:
                return result
            evidence.emit("retry", step_id=step.id, action=step.action, status="RETRYING", attempt=attempt)
            await self.surface.release_targets()
            await asyncio.sleep(step.retry.delay_ms / 1000)
        raise AssertionError("Unreachable bounded retry")

    async def _attempt(self, artifact: CapabilityArtifact, step: Step,
                       inputs: Mapping[str, Scalar], outputs: dict[str, Scalar],
                       evidence: EvidenceWriter) -> RunResult | None:
        if self.handoff:
            observation = await self.surface.observe()
            if observation.dialogs:
                return self._failure(evidence.run_id, step.id, Status.HUMAN_REQUIRED,
                                     "UNEXPECTED_BLOCKING_UI", condition=step.precondition)
        if step.precondition:
            result = await self._checkpoint(artifact, step.precondition, evidence, step.id, step.timeout_ms)
            if result:
                return result
        self._active_condition = None
        resolved = await self.resolver.resolve(step.target, self.surface)
        evidence.resolution(resolved, step.id)
        if not resolved.succeeded:
            status = Status.HUMAN_REQUIRED if resolved.code == "AMBIGUOUS_TARGET" else Status.HARD_FAILURE
            return self._failure(evidence.run_id, step.id, status, resolved.code)
        if resolved.target is None:
            return self._failure(evidence.run_id, step.id, Status.HARD_FAILURE, "NO_TARGET")
        policy = self.policy.evaluate(artifact, step, resolved)
        evidence.emit("policy", step_id=step.id, action=step.action, status=policy.decision)
        if policy.decision != Decision.ALLOW:
            status = Status.HUMAN_REQUIRED if policy.decision == Decision.REQUIRE_HUMAN else Status.HARD_FAILURE
            result = self._failure(evidence.run_id, step.id, status, policy.code, condition=step.postcondition)
            return result
        extracted = None
        self._action_attempted = step.action != Action.WAIT
        if step.action == Action.FILL:
            assert step.input is not None  # Guaranteed by Step.action_fields validation.
            await self.surface.fill(resolved.target, render(step.input, inputs), step.timeout_ms)
        elif step.action == Action.CLICK:
            await self.surface.click(resolved.target, step.timeout_ms)
        elif step.action == Action.EXTRACT:
            extracted = await self.surface.extract(resolved.target, step.timeout_ms)
        elif step.action == Action.WAIT:
            # ConditionEvaluator waits semantically and also detects business outcomes.
            pass
        if step.postcondition:
            result = await self._checkpoint(artifact, step.postcondition, evidence, step.id, step.timeout_ms)
            if result:
                return result
        else:
            for outcome in artifact.business_outcomes:
                checked = await self.conditions.check(outcome.condition, self.surface, evidence, step.id)
                if checked.ambiguous:
                    return self._failure(evidence.run_id, step.id, Status.HUMAN_REQUIRED, "AMBIGUOUS_TARGET")
                if checked.satisfied:
                    return RunResult(run_id=evidence.run_id, status=Status.BUSINESS_OUTCOME, business_code=outcome.code)
        if step.output:
            try:
                outputs[step.output] = validate_value(artifact.outputs[step.output], extracted, extracted=True)
            except ValueValidationError:
                return self._failure(evidence.run_id, step.id, Status.HARD_FAILURE, "INVALID_OUTPUT")
        return None

    async def _checkpoint(self, artifact: CapabilityArtifact, condition: Condition,
                          evidence: EvidenceWriter, step_id: str | None,
                          timeout_ms: int) -> RunResult | None:
        self._active_condition = condition
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                checked = await self.conditions.wait(condition, artifact.business_outcomes, self.surface,
                                                     evidence, step_id, timeout_ms)
        except (SurfaceTimeout, TimeoutError):
            return self._failure(evidence.run_id, step_id, Status.RECOVERABLE_ERROR,
                                 "CONDITION_TIMEOUT", condition=condition)
        evidence.emit("condition", step_id=step_id, condition_id=condition.id, status=checked.observed)
        if checked.business_code:
            return RunResult(run_id=evidence.run_id, status=Status.BUSINESS_OUTCOME, business_code=checked.business_code)
        if checked.ambiguous:
            return self._failure(evidence.run_id, step_id, Status.HUMAN_REQUIRED, "AMBIGUOUS_TARGET", condition=condition)
        if not checked.satisfied:
            return self._failure(evidence.run_id, step_id, Status.RECOVERABLE_ERROR, "CONDITION_TIMEOUT", condition=condition)
        return None

    @staticmethod
    def _failure(run_id: str, step_id: str | None, status: Status, code: str,
                 condition: Condition | None = None) -> RunResult:
        next_action = {
            Status.HUMAN_REQUIRED: "Request operator review; do not continue automatically",
            Status.RECOVERABLE_ERROR: "Inspect current UI and evidence before retrying; the action may have completed",
            Status.HARD_FAILURE: "Review the artifact, inputs, surface, and evidence before a new run",
        }[status]
        return RunResult(run_id=run_id, status=status,
            resume=ResumeInfo(blocked_step_id=step_id, reason_code=code,
                              checkpoint_ids=[condition.id] if condition else [])
                   if status == Status.HUMAN_REQUIRED and step_id else None,
            failure=Failure(
            run_id=run_id, step_id=step_id, code=code,
            expected_condition=condition.id if condition else None,
            observed_condition="ambiguous" if code == "AMBIGUOUS_TARGET" else "not_verified",
            retryable=status == Status.RECOVERABLE_ERROR, safe_next_action=next_action,
        ))
