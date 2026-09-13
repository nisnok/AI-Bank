"""Strict normalization from existing replay evidence, without importing discovery."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from deterministic_ui.evidence import Event
from deterministic_ui.models import RunResult, Status
from deterministic_ui.telemetry import DriftSignal, LocatorTelemetry
from .models import EvidenceIssue, RunMetrics


class EvidenceError(ValueError):
    """Safe codes only."""


def extract_run(directory: Path) -> RunMetrics:
    try:
        return _extract(directory)
    except EvidenceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise EvidenceError("MALFORMED_OR_INCOMPLETE_EVIDENCE") from None


def _extract(directory: Path) -> RunMetrics:
    names = ["metadata.json", "events.jsonl", "result.json"]
    blobs = {name:(directory/name).read_bytes() for name in names}
    metadata = json.loads(blobs["metadata.json"])
    if metadata.get("execution_mode", "deterministic_replay") != "deterministic_replay":
        raise EvidenceError("NON_REPLAY_EVIDENCE")
    if not metadata.get("capability_id") or not metadata.get("capability_version"):
        raise EvidenceError("CAPABILITY_IDENTITY_MISSING")
    result = RunResult.model_validate_json(blobs["result.json"])
    events = [Event.model_validate_json(line) for line in blobs["events.jsonl"].splitlines() if line.strip()]
    if not events or metadata["run_id"] != result.run_id or any(e.run_id != result.run_id for e in events):
        raise EvidenceError("RUN_ID_MISMATCH")
    finished = [e for e in events if e.kind == "run_finished"]
    rejected = [e for e in events if e.kind == "compatibility_rejected"]
    if len(finished) != 1 and not (not finished and len(rejected)==1 and result.status==Status.HARD_FAILURE):
        raise EvidenceError("TERMINAL_EVENT_MISSING")
    terminal = finished[0] if finished else rejected[0]
    if finished and terminal.status != result.status:
        raise EvidenceError("RESULT_STATUS_MISMATCH")
    started = datetime.fromisoformat(metadata["started_at"].replace("Z","+00:00"))
    if started.tzinfo is None or any(event.timestamp.tzinfo is None for event in events):
        raise EvidenceError("TIMEZONE_REQUIRED")
    if any(b.timestamp < a.timestamp for a,b in zip(events,events[1:])):
        raise EvidenceError("EVENT_ORDER_INVALID")

    # Only action-target resolutions enter locator rates. Expected-absent business
    # probes and repeated checkpoint polling must not distort those denominators.
    pending = {}
    attempts = primary = fallback = depth = 0
    ambiguous = set()
    for event in events:
        key=(event.step_id,event.condition_id)
        if event.kind=="locator_attempt":
            if event.strategy_index==0:
                pending[key]=[]
            if key not in pending or event.strategy_index != len(pending[key]):
                raise EvidenceError("INVALID_LOCATOR_SEQUENCE")
            pending[key].append(event)
        elif event.kind=="locator_result":
            ladder=pending.pop(key,[])
            if not ladder:
                raise EvidenceError("LOCATOR_ATTEMPTS_MISSING")
            if event.status=="AMBIGUOUS_TARGET":
                ambiguous.add(key)
            if event.condition_id is None and event.step_id is not None:
                attempts+=1
                primary+=int(ladder[0].status=="unique")
                used_depth=ladder[-1].strategy_index or 0
                depth=max(depth,used_depth)
                fallback+=int(event.status=="RESOLVED" and used_depth>0)
    if pending:
        raise EvidenceError("INCOMPLETE_LOCATOR_RESOLUTION")

    telemetry_path=directory/"locator-telemetry.json"
    signals=[]
    if telemetry_path.exists():
        blobs["locator-telemetry.json"]=telemetry_path.read_bytes()
        telemetry=json.loads(blobs["locator-telemetry.json"])
        resolutions=[LocatorTelemetry.model_validate(item) for item in telemetry["resolutions"]]
        signals=[DriftSignal.model_validate(item) for item in telemetry["drift_signals"]]
        for record in [*resolutions,*signals]:
            if (record.run_id != result.run_id or record.capability_id != metadata["capability_id"]
                or record.capability_version != metadata["capability_version"]
                or record.tenant_id != metadata.get("tenant_id") or record.execution_result != result.status):
                raise EvidenceError("TELEMETRY_IDENTITY_MISMATCH")
    elif metadata.get("tenant_id"):
        raise EvidenceError("TENANT_TELEMETRY_MISSING")

    retries=[e for e in events if e.kind=="retry"]
    retried_steps={e.step_id for e in retries}
    recovered=sum(1 for step in retried_steps if any(e.kind=="step_finished" and e.step_id==step
                  and e.status in {Status.SUCCESS,Status.BUSINESS_OUTCOME} for e in events))
    terminal_recoverable=int(result.status==Status.RECOVERABLE_ERROR)
    # Existing evidence records retry decisions but not every recoverable exception.
    # Count known recoverable attempts (each retry plus a terminal recoverable failure).
    recoverable=len(retries)+terminal_recoverable
    validation=[e for e in events if e.kind=="run_purpose" and e.status=="VALIDATION"]
    return RunMetrics(run_id=result.run_id, capability_id=metadata["capability_id"],
        capability_version=metadata["capability_version"], tenant_id=metadata.get("tenant_id","unattributed"),
        binding_version=metadata.get("binding_version"), started_at=started,
        completed_at=max(e.timestamp for e in events), status=result.status,
        duration_ms=Decimal(str(terminal.duration_ms)) if terminal.duration_ms is not None else None,
        step_count=sum(e.kind=="step_started" for e in events),
        primary_locator_attempts=attempts, primary_locator_successes=primary,
        fallback_locator_successes=fallback, maximum_fallback_depth=depth,
        ambiguity_count=len(ambiguous), recoverable_error_count=recoverable,
        recovery_attempts=len(retries), successful_recovery_count=recovered,
        human_handoff_count=sum(e.kind=="handoff_requested" for e in events),
        human_action_count=result.human_action_count,
        drift_signal_count=len({(s.step_id,s.condition_id,s.reason) for s in signals}),
        validation_outcome=result.status if validation else None,
        model_calls=result.model_calls, evidence_directory=str(directory),
        evidence_digest=sha256(b"".join(name.encode()+blobs[name] for name in sorted(blobs))).hexdigest())


def load_runs(root: Path, capability_id: str, version: str) -> tuple[list[RunMetrics], list[EvidenceIssue]]:
    runs,issues=[],[]
    seen=set()
    for metadata_path in sorted(root.rglob("metadata.json")):
        directory=metadata_path.parent
        try:
            metadata=json.loads(metadata_path.read_text())
            if (metadata.get("capability_id"),metadata.get("capability_version")) != (capability_id,version):
                continue
            if metadata.get("execution_mode","deterministic_replay")!="deterministic_replay":
                continue
            run=extract_run(directory)
            if run.run_id in seen:
                raise EvidenceError("DUPLICATE_RUN_ID")
            seen.add(run.run_id)
            runs.append(run)
        except (OSError,ValueError,TypeError,AttributeError) as error:
            issues.append(EvidenceIssue(evidence_directory=str(directory),
                code=str(error) if isinstance(error,EvidenceError) else "MALFORMED_METADATA"))
    return sorted(runs,key=lambda run:(run.completed_at,run.run_id)),issues
