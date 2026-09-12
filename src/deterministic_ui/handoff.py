"""Audited operator control and verified handback around a suspended replay."""
import asyncio
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import Field

from .conditions import ConditionEvaluator
from .control import ControlOwner, SessionController
from .evidence import EvidenceWriter
from .handoff_port import HandoffHandler, ResumeDisposition
from .models import (Action, CapabilityArtifact, Condition, Model, ResumeInfo, Risk,
                     RunResult, Scalar, SemanticTarget, Status, Step)
from .resolver import LocatorResolver
from .surface import SurfaceError
from .templates import render


class HandoffState(StrEnum):
    AUTOMATION = "AUTOMATION"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    PAUSED = "PAUSED"
    HUMAN_CONTROL = "HUMAN_CONTROL"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OperatorAction(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    target: SemanticTarget
    action: Action = Action.CLICK
    irreversible: bool = False
    preconditions: list[Condition] = Field(default_factory=list)
    postconditions: list[Condition] = Field(default_factory=list)


class ResumePlan(Model):
    completed: list[Condition] = Field(default_factory=list)
    retry: list[Condition] = Field(default_factory=list)
    actions: list[OperatorAction] = Field(default_factory=list)


class HandoffManager(HandoffHandler):
    """One run, one retained session. Operator actions are explicitly allowlisted."""
    def __init__(self, controller: SessionController, plans: dict[str, ResumePlan], *,
                 input_source: str = "operator_panel"):
        self.controller = controller
        self.plans = plans
        self.input_source = input_source
        self.state = HandoffState.AUTOMATION
        self.pending: RunResult | None = None
        self.human_action_count = 0
        self.handoff_occurred = False
        self._evidence: EvidenceWriter | None = None
        self._plan = ResumePlan()
        self._wake = asyncio.Event()
        self._cancelled = False
        self._inputs: dict[str, Scalar] = {}
        self._used_mutations: set[str] = set()
        self._handoff_number = 0
        self._pause_automation_count = 0
        self._ownership_checks: list[dict] = []

    def _emit(self, kind, **fields):
        assert self._evidence is not None
        self._evidence.emit(kind, session_id=self.controller.session_id,
                            control_owner=self.controller.owner, **fields)

    def _bind(self, condition: Condition) -> Condition:
        if condition.expected.value is None:
            return condition
        return condition.model_copy(update={"expected": condition.expected.model_copy(
            update={"value": render(condition.expected.value, self._inputs)})})

    async def _checks(self, conditions: list[Condition], surface, *, wait=False) -> bool:
        if not conditions:
            return False
        assert self._evidence is not None
        evaluator = ConditionEvaluator(LocatorResolver())
        original_context = self._evidence.context
        self._evidence.context = original_context.model_copy(update={"actor": self.controller.owner.value})
        try:
            for condition in conditions:
                condition = self._bind(condition)
                if wait:
                    result = await evaluator.wait(condition, [], surface, self._evidence, None, 2000)
                else:
                    result = await evaluator.check(condition, surface, self._evidence, None)
                if result.ambiguous or not result.satisfied:
                    return False
            return True
        finally:
            self._evidence.context = original_context

    async def resolve(self, artifact: CapabilityArtifact, step: Step, result: RunResult,
                      inputs: dict[str, Scalar], evidence: EvidenceWriter) -> ResumeDisposition:
        self._evidence, self._inputs = evidence, inputs
        self._plan = self.plans.get(step.id, ResumePlan())
        self._handoff_number += 1
        self.handoff_occurred = True
        self.state = HandoffState.HUMAN_REQUIRED
        resume = ResumeInfo(blocked_step_id=step.id,
            reason_code=result.failure.code if result.failure else "HUMAN_REQUIRED",
            checkpoint_ids=[c.id for c in [*self._plan.completed, *self._plan.retry]],
            evidence_ref=str(evidence.events_path))
        self.pending = result.model_copy(update={"resume": resume, "outputs": {}})
        evidence.write_json(f"handoff-{self._handoff_number}.json", self.pending.model_dump(mode="json"))
        self._emit("handoff_requested", step_id=step.id, status=resume.reason_code)
        self.state = HandoffState.PAUSED
        self._emit("automation_paused", step_id=step.id, status=self.state)
        self._pause_automation_count = self.controller.action_counts[ControlOwner.AUTOMATION]
        await evidence.screenshot(self.controller.automation, f"handoff_{self._handoff_number}")
        while True:
            await self._wake.wait()
            self._wake.clear()
            if self._cancelled:
                self.state = HandoffState.FAILED
                return ResumeDisposition.STOP
            surface = self.controller.automation
            observation = await surface.observe()
            self._emit("resume_observation", step_id=step.id,
                       status="BLOCKING_DIALOG" if observation.dialogs else "FRESH_OBSERVATION")
            await evidence.screenshot(surface, f"handback_{self._handoff_number}_{self.human_action_count}")
            completed = [*self._plan.completed]
            if step.postcondition:
                completed.append(step.postcondition)
            if (self._plan.completed and not step.output and not observation.dialogs
                and await self._checks(completed, surface, wait=True)):
                self._emit("resume_checkpoint_verified", step_id=step.id, status="COMPLETED_STEP")
                self.state = HandoffState.AUTOMATION
                self._emit("resumed", step_id=step.id, status="COMPLETED_STEP")
                return ResumeDisposition.COMPLETED_STEP
            # Only a known pre-dispatch block permits re-executing a reversible/read step.
            retry_allowed = (resume.reason_code in {"AMBIGUOUS_TARGET", "UNEXPECTED_BLOCKING_UI"}
                             and result.failure is not None and not result.failure.action_attempted)
            if (retry_allowed and step.risk in {Risk.READ, Risk.REVERSIBLE_WRITE}
                and not observation.dialogs and await self._checks(self._plan.retry, surface)):
                self._emit("resume_checkpoint_verified", step_id=step.id, status="RETRY_STEP")
                self.state = HandoffState.AUTOMATION
                self._emit("resumed", step_id=step.id, status="RETRY_STEP")
                return ResumeDisposition.RETRY_STEP
            self.state = HandoffState.HUMAN_REQUIRED
            self._emit("resume_rejected", step_id=step.id, status="CHECKPOINT_NOT_VERIFIED")

    async def take_control(self):
        async with self.controller.lock:
            if self.state not in {HandoffState.PAUSED, HandoffState.HUMAN_REQUIRED}:
                raise SurfaceError("HANDOFF_NOT_PENDING")
            self.controller.require(ControlOwner.AUTOMATION)
            self.controller.owner = ControlOwner.HUMAN
            self.state = HandoffState.HUMAN_CONTROL
            self._emit("control_transferred", actor="HUMAN", status=self.state)

    async def human_action(self, action_id: str, value: str | None = None):
        async with self.controller.lock:
            self.controller.require(ControlOwner.HUMAN)
            if self.state != HandoffState.HUMAN_CONTROL:
                raise SurfaceError("HUMAN_CONTROL_REQUIRED")
            action = next((item for item in self._plan.actions if item.id == action_id), None)
            if action is None or action.action not in {Action.CLICK, Action.FILL}:
                raise SurfaceError("UNSUPPORTED_OPERATOR_ACTION")
            if action.irreversible and action.id in self._used_mutations:
                raise SurfaceError("MUTATION_ALREADY_ATTEMPTED_VERIFY_STATE")
            raw = self.controller._surface
            if action.preconditions and not await self._checks(action.preconditions, raw):
                raise SurfaceError("OPERATOR_PRECONDITION_NOT_VERIFIED")
            resolved = await LocatorResolver().resolve(action.target, raw)
            if not resolved.succeeded or resolved.target is None:
                raise SurfaceError("OPERATOR_TARGET_NOT_UNIQUE")
            if action.action == Action.FILL and value is None:
                raise SurfaceError("VALUE_REQUIRED")
            before = await raw.observe()
            assert self._evidence is not None
            self.human_action_count += 1
            number = self.human_action_count
            # Persist intent before dispatch; uncertain actions cannot silently disappear.
            self._emit("human_action_started", actor="HUMAN", action=action.action, status=action.id)
            if action.irreversible:
                self._used_mutations.add(action.id)
            outcome = "UNCERTAIN"
            try:
                self.controller.action_counts[ControlOwner.HUMAN] += 1
                if action.action == Action.CLICK:
                    await raw.click(resolved.target, 3000)
                else:
                    assert value is not None
                    await raw.fill(resolved.target, value, 3000)
                outcome = "EXECUTED"
                if action.postconditions:
                    outcome = "VERIFIED" if await self._checks(action.postconditions, raw, wait=True) else "NOT_VERIFIED"
            except SurfaceError:
                outcome = "UNCERTAIN"
            finally:
                after = await raw.observe()
                screenshot = await self._evidence.screenshot(raw, f"human_{number}")
                record = {
                    "actor": "HUMAN", "input_source": self.input_source,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "run_id": self._evidence.run_id, "session_id": self.controller.session_id,
                    "action": action.action, "target": action.id,
                    "target_kind": "configured_semantic_target",
                    "before": {**self._redact(before), "verified_conditions": [c.id for c in action.preconditions]},
                    "after": {**self._redact(after), "verified_conditions": [c.id for c in action.postconditions] if outcome == "VERIFIED" else []},
                    "value": "[redacted]" if value is not None else None,
                    "status": outcome, "screenshot": screenshot,
                }
                self._evidence.write_json(f"human-action-{number}.json", record)
                self._emit("human_action", actor="HUMAN", action=action.action, status=outcome,
                           evidence_ref=f"human-action-{number}.json")
                await raw.release_targets()
            return outcome

    @staticmethod
    def _redact(observation):
        # State counts are useful audit context without retaining text, URLs, or values.
        return {"visible": observation.visible, "element_count": len(observation.elements),
                "dialog_count": len(observation.dialogs), "text": "[redacted]"}

    async def handback(self):
        async with self.controller.lock:
            self.controller.require(ControlOwner.HUMAN)
            if self.state != HandoffState.HUMAN_CONTROL:
                raise SurfaceError("HUMAN_CONTROL_REQUIRED")
            self._emit("handback_requested", actor="HUMAN")
            if self.controller.action_counts[ControlOwner.AUTOMATION] != self._pause_automation_count:
                raise SurfaceError("AUTOMATION_ACTED_DURING_HANDOFF")
            self._ownership_checks.append({"handoff": self._handoff_number,
                                           "automation_actions_during_human_control": 0})
            self.controller.owner = ControlOwner.AUTOMATION
            self.state = HandoffState.RESUMING
            self._emit("control_returned", status=self.state)
            self._wake.set()

    async def cancel(self):
        async with self.controller.lock:
            if self.state not in {HandoffState.HUMAN_CONTROL, HandoffState.PAUSED, HandoffState.HUMAN_REQUIRED}:
                raise SurfaceError("NO_PENDING_HANDOFF")
            self._cancelled = True
            self.controller.owner = ControlOwner.AUTOMATION
            self._emit("handoff_cancelled", actor="HUMAN", status="STOP")
            self._wake.set()

    async def status(self):
        async with self.controller.lock:
            observation = await self.controller._surface.observe()
            return {"state": self.state, "owner": self.controller.owner,
                    "session_id": self.controller.session_id,
                    "reason": self.pending.resume.reason_code if self.pending and self.pending.resume else None,
                    "step": self.pending.resume.blocked_step_id if self.pending and self.pending.resume else None,
                    "actions": [{"id": a.id, "label": a.label} for a in self._plan.actions],
                    "page_text": observation.text,  # Live local display only, never disk evidence.
                    "human_action_count": self.human_action_count}

    def finished(self, result):
        self.state = HandoffState.COMPLETED if result.status == Status.SUCCESS else HandoffState.FAILED
        if self._evidence:
            self._evidence.write_json("control-summary.json", {
                "session_id": self.controller.session_id,
                "input_source": self.input_source,
                "handoff_count": self._handoff_number,
                "human_action_count": self.human_action_count,
                "ownership_checks": self._ownership_checks,
                "action_counts": self.controller.action_counts,
                "status": result.status,
            })
            self._emit("final_result", status=result.status, model_calls=0)
