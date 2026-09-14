# 3. Different input, zero LLM calls

**What this proves:** Discovery input A → compiled capability → different input B → correct deterministic replay, with **ZERO model calls**.

**What happened:** After discovery, the Primary reviewer run started a fresh worker with another fictional member input. ReplayEngine executed the generated capability against a new browser session. The worker removed model credentials, blocked model imports and checked the expected member identity and exact Decimal balance in memory.

**Best evidence files:**

- [Pipeline report](../acceptance/key-retry-20260914-1/report.json), especially `claims.zero_model_replay`: `different_member`, `identity_verified` and `balance_verified` are true; `model_calls` is 0; credentials are absent; loaded model modules are empty; import guard is enabled.
- [Replay metadata](../acceptance/key-retry-20260914-1/validation/a7e113edc24045959dd31b58116d18a2/metadata.json), [events](../acceptance/key-retry-20260914-1/validation/a7e113edc24045959dd31b58116d18a2/events.jsonl) and [result](../acceptance/key-retry-20260914-1/validation/a7e113edc24045959dd31b58116d18a2/result.json): deterministic execution mode, actual step/checkpoint sequence and SUCCESS.
- [Redacted final screen](../acceptance/key-retry-20260914-1/validation/a7e113edc24045959dd31b58116d18a2/screenshots/final.png): visible workflow context, with member and balance values masked.

**Result:** Different-input replay passed with zero model calls. Empty persisted outputs are intentional privacy protection, not a missing result: the report records that returned values were verified in memory.

**Why it matters:** The capability generalizes beyond the discovery input, and execution does not depend on model availability or new model decisions. This run's isolation checks complement the [dependency-boundary tests](../../tests/test_boundaries.py); they are not an OS-level sandbox claim.

[Next: failure handling and handoff](04_failure_and_handoff.md) · [All five proofs](../README.md)
