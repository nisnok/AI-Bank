"""Bounded model-driven actions. Never imports ReplayEngine or loads capabilities."""
import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from pydantic import ValidationError

from deterministic_ui.evidence import EvidenceContext, EvidenceWriter
from deterministic_ui.models import Decision, FieldSpec, Observation, Risk
from deterministic_ui.policy import PolicyEngine
from deterministic_ui.resolver import LocatorResolver
from deterministic_ui.surface import Surface, SurfaceError
from deterministic_ui.templates import ValueValidationError, validate_value
from .evidence import DiscoveryEvidence, fingerprint
from .model_client import InvalidModelOutput, ModelClient, ModelError
from .models import (DiscoveryAction as A, DiscoveryLimits, DiscoveryRequest, DiscoveryResult,
                     DiscoveryStatus as S, HistoryItem, ModelReply, TrajectoryStep, Usage)
from .safety import business_outcome, classify, member_matches


@dataclass
class ActionProgress:
    step: TrajectoryStep


class DiscoveryOrchestrator:
    def __init__(self, surface: Surface, model: ModelClient, *, policy: PolicyEngine | None = None,
                 limits: DiscoveryLimits | None = None, evidence_root: Path = Path('evidence/discovery')):
        self.surface, self.model = surface, model
        self.policy = policy or PolicyEngine()
        self.limits = limits or DiscoveryLimits()
        self.evidence_root = evidence_root
        self.resolver = LocatorResolver()
        self._lock = asyncio.Lock()

    async def execute(self, request: DiscoveryRequest) -> DiscoveryResult:
        async with self._lock:
            return await self._run(request)

    async def _run(self, request: DiscoveryRequest) -> DiscoveryResult:
        started = monotonic()
        run_id = uuid4().hex
        calls = 0
        usage = Usage()
        trajectory: list[TrajectoryStep] = []
        history: list[HistoryItem] = []
        outputs = {}
        status, code = S.HARD_FAILURE, 'NOT_STARTED'
        writer = None
        evidence = None
        try:
            writer = EvidenceWriter(self.evidence_root, run_id, context=EvidenceContext(
                execution_mode='llm_discovery', actor='MODEL', provider=self.model.provider,
                model=self.model.model, goal='Find member [MEMBER_ID] and retrieve their savings balance.'))
            evidence = DiscoveryEvidence(writer, request)
            writer.emit('run_started', status='RUNNING')
            repeats: dict[tuple[str, str, str | None], int] = {}
            failures = 0
            async with asyncio.timeout(self.limits.max_seconds):
                for sequence in range(1, self.limits.max_decisions + 1):
                    await self.surface.release_targets()
                    observation = await self.surface.observe()
                    writer.write_json(f'observation-{sequence:03d}.json', evidence.observation(observation))
                    if business := business_outcome(observation):
                        status, code = S.BUSINESS_OUTCOME, business
                        break
                    if observation.dialogs:
                        status, code = S.HUMAN_REQUIRED, 'DIALOG_PRESENT'
                        break
                    calls += 1
                    writer.emit('model_call', model_calls=calls, status='STARTED')
                    try:
                        reply = await self.model.decide(request.goal, observation, history,
                                                       [action for action in A if action != A.SELECT or 'select' in self.surface.features])
                        # Revalidate even if an adapter used model_construct/model_copy without validation.
                        reply = ModelReply.model_validate(reply.model_dump(warnings=False))
                    except (InvalidModelOutput, ValidationError):
                        writer.emit('model_decision', status='INVALID_MODEL_OUTPUT', model_calls=calls)
                        status, code = S.HARD_FAILURE, 'INVALID_MODEL_OUTPUT'
                        break
                    except ModelError as exc:
                        transient = {'PROVIDER_HTTP_429', 'PROVIDER_HTTP_500', 'PROVIDER_HTTP_503', 'PROVIDER_CONNECTION_ERROR'}
                        if str(exc) not in transient:
                            raise
                        failures += 1
                        writer.emit('model_error', status=str(exc), model_calls=calls, attempt=failures)
                        if failures >= self.limits.failure_limit:
                            status, code = S.HARD_FAILURE, 'MODEL_FAILURE_LIMIT'
                            break
                        # Retry the decision, never replay a UI action. Both the decision
                        # budget and elapsed-time deadline include these provider attempts.
                        await asyncio.sleep(2)
                        continue
                    usage = Usage(input_tokens=usage.input_tokens + reply.usage.input_tokens,
                                  output_tokens=usage.output_tokens + reply.usage.output_tokens,
                                  thinking_tokens=usage.thinking_tokens + reply.usage.thinking_tokens)
                    decision = reply.decision
                    writer.emit('model_decision', action=decision.action, status='VALIDATED', model_calls=calls,
                                input_tokens=reply.usage.input_tokens, output_tokens=reply.usage.output_tokens)
                    key = (fingerprint(observation), decision.action.value, decision.target_id)
                    repeats[key] = repeats.get(key, 0) + 1
                    step = TrajectoryStep(sequence=sequence, before=observation, decision=decision, prior_failures=failures)
                    step_started = monotonic()
                    progress = ActionProgress(step)
                    terminal = None
                    try:
                        if repeats[key] >= self.limits.repeat_limit:
                            step = step.model_copy(update={'status':'STUCK'})
                            terminal = (S.STUCK, 'REPEATED_STATE_ACTION')
                        elif decision.action == A.COMPLETE:
                            latest = await self.surface.observe()
                            balances = [el for el in latest.elements if el.name == 'Savings balance' and el.visible]
                            current_balance = validate_value(FieldSpec(type='decimal'), balances[0].text.strip()) if len(balances) == 1 else None
                            if 'savings_balance' in outputs and member_matches(latest, request.member_id) and outputs['savings_balance'] == current_balance:
                                step = step.model_copy(update={'status':'COMPLETE', 'verified':True})
                                terminal = (S.SUCCESS, 'VERIFIED_BALANCE')
                            else:
                                step = step.model_copy(update={'status':'UNVERIFIED_COMPLETION'})
                                terminal = (S.HARD_FAILURE, 'UNVERIFIED_COMPLETION')
                        elif decision.action in {A.FAIL, A.REQUEST_HUMAN}:
                            terminal = (S.HUMAN_REQUIRED if decision.action == A.REQUEST_HUMAN else S.HARD_FAILURE, decision.action.value)
                            step = step.model_copy(update={'status':decision.action.value})
                        else:
                            async with asyncio.timeout(self.limits.action_timeout_ms / 1000):
                                step, captured, terminal = await self._act(request, progress, writer)
                            if captured is not None and step.verified:
                                outputs['savings_balance'] = captured
                    except (TimeoutError, SurfaceError, ValueValidationError):
                        step = progress.step.model_copy(update={'status':'ACTION_NOT_VERIFIED', 'compilation_eligible':False})
                    # A timed-out action may already have affected the UI. No automatic retry;
                    # the next bounded model decision sees the actual state and failure history.
                    step = step.model_copy(update={'duration_ms':round((monotonic() - step_started) * 1000, 3)})
                    trajectory.append(step)
                    evidence.record(step)
                    writer.emit('discovery_step', step_id=str(sequence), action=decision.action,
                                status=step.status, duration_ms=step.duration_ms)
                    await writer.screenshot(self.surface, str(sequence))
                    history.append(HistoryItem(action=decision.action, target_id=decision.target_id,
                                               status=step.status,
                                               output_captured=decision.output if step.verified else None))
                    if terminal:
                        status, code = terminal
                        break
                    failures = 0 if step.verified else failures + 1
                    if failures >= self.limits.failure_limit:
                        status, code = S.STUCK, 'REPEATED_FAILURES'
                        break
                else:
                    status, code = S.MAX_STEPS_EXCEEDED, 'DECISION_LIMIT'
        except TimeoutError:
            status, code = S.HARD_FAILURE, 'ELAPSED_TIME_LIMIT'
        except ModelError as exc:
            status = S.HARD_FAILURE
            # Provider clients are trusted to emit safe error codes, not raw messages.
            code = str(exc) if str(exc).startswith(('PROVIDER_', 'GEMINI_', 'INVALID_', 'MOCK_')) and len(str(exc)) < 80 else 'MODEL_ERROR'
        except OSError:
            status, code = S.HARD_FAILURE, 'EVIDENCE_UNAVAILABLE'
        except Exception:
            status, code = S.HARD_FAILURE, 'DISCOVERY_ERROR'
        finally:
            try:
                await self.surface.release_targets()
            except Exception:
                pass
        result = DiscoveryResult(run_id=run_id, status=status, code=code, goal=request.goal,
                                 provider=self.model.provider, model=self.model.model, model_calls=calls,
                                 usage=usage, latency_ms=round((monotonic() - started)*1000, 3),
                                 outputs=outputs if status == S.SUCCESS else {}, trajectory=trajectory,
                                 evidence_directory=str(self.evidence_root / run_id))
        if writer and evidence:
            try:
                writer.emit('run_finished', status=status, model_calls=calls, duration_ms=result.latency_ms)
                evidence.finish(result)
            except OSError:
                result = result.model_copy(update={'status':S.HARD_FAILURE, 'code':'EVIDENCE_UNAVAILABLE', 'outputs':{}})
        return result

    async def _act(self, request: DiscoveryRequest, progress: ActionProgress, writer: EvidenceWriter):
        step = progress.step
        decision = step.decision
        if decision.action == A.SELECT and 'select' not in self.surface.features:
            return step.model_copy(update={'status':'UNSUPPORTED_ACTION'}), None, (S.HARD_FAILURE, 'UNSUPPORTED_ACTION')
        if decision.action == A.WAIT:
            policy = self.policy.evaluate_risk(Risk.READ, unreviewed=True)
            writer.emit('policy', step_id=str(step.sequence), action=decision.action, status=policy.decision)
            if policy.decision != Decision.ALLOW:
                return step.model_copy(update={'status':policy.code}), None, (S.HARD_FAILURE, policy.code)
            progress.step = step.model_copy(update={'attempted':True, 'executed':True})
            after = await self._wait_text(decision.expected_text or '')
            verified = (decision.expected_text or '').casefold() in after.text.casefold()
            return progress.step.model_copy(update={'verified':verified, 'compilation_eligible':verified,
                                          'after':after, 'postcondition':'expected_text_visible' if verified else 'not_verified',
                                          'status':'VERIFIED' if verified else 'ACTION_NOT_VERIFIED'}), None, None
        matches = [el for el in step.before.elements if el.id == decision.target_id]
        if len(matches) != 1:
            return step.model_copy(update={'status':'UNKNOWN_OBSERVATION_TARGET'}), None, (S.HARD_FAILURE, 'UNKNOWN_OBSERVATION_TARGET')
        element = matches[0]
        fresh = await self.surface.observe()
        if fingerprint(fresh) != fingerprint(step.before):
            return step.model_copy(update={'status':'OBSERVATION_CHANGED', 'after':fresh}), None, None
        resolution = await self.resolver.resolve(element.target, self.surface)
        writer.resolution(resolution, str(step.sequence))
        step = step.model_copy(update={'target':element.target, 'resolution':resolution})
        progress.step = step
        if not resolution.succeeded or resolution.target is None:
            status = S.HUMAN_REQUIRED if resolution.code == 'AMBIGUOUS_TARGET' else S.HARD_FAILURE
            return step.model_copy(update={'status':resolution.code}), None, (status, resolution.code)
        policy = self.policy.evaluate_operation(classify(decision.action, element), resolution, unreviewed=True)
        writer.emit('policy', step_id=str(step.sequence), action=decision.action, status=policy.decision)
        if policy.decision != Decision.ALLOW:
            status = S.HUMAN_REQUIRED if policy.decision == Decision.REQUIRE_HUMAN else S.HARD_FAILURE
            return step.model_copy(update={'status':policy.code}), None, (status, policy.code)
        if not element.enabled:
            return step.model_copy(update={'status':'DISABLED_TARGET'}), None, (S.HUMAN_REQUIRED, 'DISABLED_TARGET')
        captured = None
        if decision.action in {A.FILL, A.SELECT}:
            if decision.input_binding != 'member_id':
                return step.model_copy(update={'status':'UNKNOWN_INPUT'}), None, (S.HARD_FAILURE, 'UNKNOWN_INPUT')
            if decision.action == A.FILL:
                progress.step = step.model_copy(update={'attempted':True})
                await self.surface.fill(resolution.target, request.member_id, self.limits.action_timeout_ms)
            else:
                progress.step = step.model_copy(update={'attempted':True})
                await self.surface.select(resolution.target, request.member_id, self.limits.action_timeout_ms)
            progress.step = progress.step.model_copy(update={'executed':True})
            after = await self.surface.observe()
            matching = [el for el in after.elements if el.target == element.target]
            verified = len(matching) == 1 and matching[0].value == request.member_id
        elif decision.action == A.CLICK:
            progress.step = step.model_copy(update={'attempted':True})
            await self.surface.click(resolution.target, self.limits.action_timeout_ms)
            progress.step = progress.step.model_copy(update={'executed':True})
            after = await self._wait_text(decision.expected_text or '')
            verified = (fingerprint(after) != fingerprint(step.before)
                        and (decision.expected_text or '').casefold() in after.text.casefold())
        elif decision.action == A.EXTRACT:
            if decision.output != 'savings_balance' or element.name != 'Savings balance' or not member_matches(step.before, request.member_id):
                return step.model_copy(update={'status':'UNVERIFIED_MEMBER_OR_OUTPUT'}), None, (S.HUMAN_REQUIRED, 'UNVERIFIED_MEMBER_OR_OUTPUT')
            progress.step = step.model_copy(update={'attempted':True})
            raw = await self.surface.extract(resolution.target, self.limits.action_timeout_ms)
            progress.step = progress.step.model_copy(update={'executed':True})
            captured = validate_value(FieldSpec(type='decimal'), raw, extracted=True)
            after = await self.surface.observe()
            verified = member_matches(after, request.member_id)
        else:
            return step.model_copy(update={'status':'UNSUPPORTED_ACTION'}), None, (S.HARD_FAILURE, 'UNSUPPORTED_ACTION')
        return progress.step.model_copy(update={'verified':verified, 'compilation_eligible':verified,
                                      'after':after, 'postcondition':'observed_effect' if verified else 'not_verified',
                                      'status':'VERIFIED' if verified else 'ACTION_NOT_VERIFIED'}), captured, None

    async def _wait_text(self, expected: str) -> Observation:
        while True:
            observation = await self.surface.observe()
            if expected.casefold() in observation.text.casefold() or business_outcome(observation) or observation.dialogs:
                return observation
            await asyncio.sleep(0.05)
