"""Allowlisted evidence: no raw inputs, outputs, UI text, or exception strings."""
from datetime import datetime, timezone
from pathlib import Path
import json

from pydantic import Field

from .models import Action, CapabilityArtifact, Model, ResolutionResult, RunResult
from .surface import Surface
from .telemetry import DriftSignal, LocatorTelemetry


class Event(Model):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str
    execution_mode: str = "deterministic_replay"
    actor: str = "replay_engine"
    kind: str
    step_id: str | None = None
    action: str | None = None
    strategy: str | None = None
    strategy_index: int | None = None
    matches: int | None = None
    quality: str | None = None
    duration_ms: float | None = None
    status: str | None = None
    attempt: int | None = None
    condition_id: str | None = None
    evidence_ref: str | None = None
    model_calls: int | None = None
    session_id: str | None = None
    control_owner: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class EvidenceContext(Model):
    execution_mode: str = "deterministic_replay"
    actor: str = "replay_engine"
    provider: str | None = None
    model: str | None = None
    goal: str | None = None
    tenant_id: str | None = None
    binding_version: str | None = None
    canonical_digest: str | None = None
    binding_digest: str | None = None
    product: str | None = None
    observed_application_version: str | None = None
    observed_product: str | None = None
    observed_tenant_id: str | None = None


class EvidenceWriter:
    def __init__(self, root: Path, run_id: str, artifact: CapabilityArtifact | None = None,
                 *, context: EvidenceContext | None = None):
        self.context = context or EvidenceContext()
        self.run_id = run_id
        self._artifact = artifact
        self._telemetry: list[LocatorTelemetry] = []
        self._step_results = {}
        self._retried = set()
        self.directory = root / run_id
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        (self.directory / "screenshots").mkdir(mode=0o700)
        self.events_path = self.directory / "events.jsonl"
        self.events_path.touch(mode=0o600)
        # Persist only artifact identity. Templates, descriptions, and selectors can contain secrets.
        self._write("metadata.json", json.dumps({
            "run_id": run_id, "capability_id": artifact.capability_id if artifact else None,
            "capability_version": artifact.capability_version if artifact else None,
            "schema_version": artifact.schema_version if artifact else None,
            **self.context.model_dump(exclude_none=True),
            "model_calls_at_start": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "redaction": "all runtime values omitted; screenshots fully masked",
        }, indent=2))

    def _write(self, name: str, contents: str) -> None:
        with (self.directory / name).open("x", encoding="utf-8") as stream:
            (self.directory / name).chmod(0o600)
            stream.write(contents)

    def emit(self, kind: str, **fields) -> None:
        if kind == "step_finished":
            self._step_results[fields.get("step_id")] = fields.get("status")
        if kind == "retry":
            self._retried.add(fields.get("step_id"))
        event = Event(run_id=self.run_id, kind=kind, execution_mode=self.context.execution_mode,
                      actor=fields.pop("actor", self.context.actor), **fields)
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(event.model_dump_json(exclude_none=True) + "\n")

    def write_json(self, name: str, value: dict) -> None:
        if Path(name).name != name:
            raise ValueError("Evidence filenames must be local")
        self._write(name, json.dumps(value, indent=2))

    def resolution(self, result: ResolutionResult, step_id: str | None,
                   condition_id: str | None = None) -> None:
        if self.context.tenant_id and self.context.binding_version and self._artifact and result.attempts:
            primary, last = result.attempts[0], result.attempts[-1]
            self._telemetry.append(LocatorTelemetry(
                run_id=self.run_id, capability_id=self._artifact.capability_id,
                capability_version=self._artifact.capability_version,
                tenant_id=self.context.tenant_id, binding_version=self.context.binding_version,
                step_id=step_id, condition_id=condition_id,
                expected_primary_strategy=primary.strategy,
                primary_strategy_succeeded=primary.diagnostic == "unique",
                strategy_used=result.strategy if result.succeeded else None,
                attempted_strategy=last.strategy, fallback_depth=last.index, match_count=result.matches,
                resolution_quality=result.quality, ambiguity=result.code == "AMBIGUOUS_TARGET",
                resolution_succeeded=result.succeeded, recovery_needed=last.index > 0))
        for attempt in result.attempts:
            self.emit("locator_attempt", step_id=step_id, condition_id=condition_id,
                      strategy=attempt.strategy, strategy_index=attempt.index,
                      matches=attempt.matches, status=attempt.diagnostic)
        self.emit("locator_result", step_id=step_id, condition_id=condition_id,
                  strategy=result.strategy, matches=result.matches,
                  quality=result.quality, status=result.code)

    async def screenshot(self, surface: Surface, step_id: str | None) -> str | None:
        name = f"screenshots/{step_id or 'final'}.png"
        try:
            await surface.screenshot(self.directory / name)
            (self.directory / name).chmod(0o600)
        except Exception:
            self.emit("screenshot", step_id=step_id, status="CAPTURE_UNAVAILABLE")
            return None
        self.emit("screenshot", step_id=step_id, status="CAPTURED", evidence_ref=name)
        return name

    def finish(self, result: RunResult) -> None:
        if self.context.tenant_id:
            records, signals = [], []
            for item in self._telemetry:
                values = item.model_dump() | {
                    "execution_result": result.status,
                    "step_execution_result": self._step_results.get(item.step_id),
                    "retry_needed": item.step_id in self._retried,
                    "recovery_needed": item.recovery_needed or item.step_id in self._retried,
                }
                record = LocatorTelemetry.model_validate(values)
                records.append(record.model_dump(mode="json"))
                if record.ambiguity or (record.resolution_succeeded and record.fallback_depth > 0):
                    signals.append(DriftSignal(**values, reason="AMBIGUOUS_TARGET" if record.ambiguity else "FALLBACK_USED").model_dump(mode="json"))
            self.write_json("locator-telemetry.json", {"resolutions":records, "drift_signals":signals})
        # Caller receives typed values; persisted result intentionally contains no values.
        redacted = result.model_copy(update={"outputs": {}})
        self._write("result.json", redacted.model_dump_json(indent=2))
