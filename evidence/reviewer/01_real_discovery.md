# 1. Real Gemini discovery

**What this proves:** A natural-language balance request drives real Gemini decisions and real Chromium actions, producing a verified trajectory.

**What happened:** In the **Primary reviewer run**, `key-retry-20260914-1`, Gemini observed the fictional simulator, selected typed FILL → CLICK → EXTRACT → COMPLETE decisions and retrieved the requested balance. Six provider calls include retries. ReplayEngine and a saved/generated capability did not drive this discovery. Decisions reference element IDs from normalized observations; the model does not supply arbitrary selectors.

**Best evidence files:**

- [Pipeline report](../acceptance/key-retry-20260914-1/report.json): discovery provider, model, call count and PASS.
- [Observed page](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/observation-004.json) and [verified extraction trajectory](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/trajectory-005.json): normalized elements, typed decision, unique semantic resolution and attempted/executed/verified flags.
- [Verified completion](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/trajectory-006.json), [result](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/result.json) and [event log](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/events.jsonl): successful trajectory and actual provider attempts, including errors.

**Result:** Real Gemini discovery passed. Runtime member/balance values and free-form reasoning are redacted on disk; successful checks are recorded rather than exposing those values. Disk trajectories are audit projections; compilation consumes the full in-memory trajectory.

**Why it matters:** The successful behavior was discovered through observed UI interactions, providing a grounded input to compilation.

[Next: compiled capability](02_compiled_capability.md) · [All five proofs](../README.md)
