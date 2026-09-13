"""Immutable derived snapshots. Source evidence remains the authority."""
from pathlib import Path
from uuid import uuid4

from .models import CapabilityHealth, RunMetrics


class HealthStore:
    def __init__(self, root: Path=Path("health")):
        self.root=root

    def save(self, summary: CapabilityHealth, runs: list[RunMetrics]) -> Path:
        if set(summary.run_ids)!={run.run_id for run in runs}:
            raise ValueError("SUMMARY_SOURCE_MISMATCH")
        directory=self.root/summary.capability_id/summary.capability_version/uuid4().hex
        directory.mkdir(parents=True,exist_ok=False,mode=0o700)
        for name,text in (
            ("summary.json",summary.model_dump_json(indent=2)),
            ("runs.jsonl","\n".join(run.model_dump_json() for run in sorted(runs,key=lambda r:(r.completed_at,r.run_id)))),
            ("thresholds.json",summary.thresholds.model_dump_json(indent=2))):
            with (directory/name).open("x") as stream:
                (directory/name).chmod(0o600)
                stream.write(text+"\n")
        return directory
