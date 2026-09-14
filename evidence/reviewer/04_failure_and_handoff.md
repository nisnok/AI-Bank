# 4. Fail safely and hand control back

**What this proves:** Expected business results, bounded operational errors and ambiguity are distinct; live human assistance uses ownership and verified resume.

**What happened:** The Primary reviewer run proves the business outcome. Supporting / historical evidence covers deliberately injected faults and handoff:

| Case | Best evidence files | Result |
|---|---|---|
| Business outcome | [Missing-member result](../acceptance/key-retry-20260914-1/business/207d75ba21b043028e953ead6f8ac000/result.json) | BUSINESS_OUTCOME / MEMBER_NOT_FOUND, not a crash; zero model calls. |
| Recoverable condition | [Recovery assertions](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/recovery/report.json) | One safe wait retry, one search submission, then RECOVERABLE_ERROR when the deadline is exhausted. This proves bounded handling, not eventual recovery success. |
| Ambiguity | [Ambiguous result](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenants/7a4701838d0e4f59ba7d2ac54c840a84/result.json) and [scenario counters](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json) | HUMAN_REQUIRED / AMBIGUOUS_TARGET; zero search submissions. |
| Discovery-time handoff | [Real Gemini handoff report](../acceptance/ca89e14b3e69427a87b8360d73f527e0/live-handoff/011a662b0bed41a498c245a379aed91e/report.json) and [event timeline](../acceptance/ca89e14b3e69427a87b8360d73f527e0/live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/events.jsonl) | Same session; one audited acknowledgement; fresh checks; discovery SUCCESS. |
| Replay handoff | [Control summary](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/control-summary.json) and [human action record](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/human-action-1.json) | Two ownership cycles; final confirmation performed once. |

The handoff sequence is automation → HUMAN_REQUIRED → retained BrowserContext/Page → HUMAN ownership → supported audited action → handback → fresh observation → trusted state checks → continuation. The discovery report records zero automation actions and model calls during HUMAN ownership and a rejected unsafe handback. [Browser verification](../../tests/test_discovery_handoff_browser.py) independently checks that Page/BrowserContext identity stays unchanged. The [redacted notice screen](../acceptance/ca89e14b3e69427a87b8360d73f527e0/live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handoff_1.png) illustrates the blocked state.

**Result:** These checks passed. Acceptance operators are explicitly scripted, including the real-Gemini handoff case; this is not a claim that a physical person clicked during acceptance. Interactive demos expose the same bounded controls.

**Why it matters:** Automation stops instead of guessing, and resume verifies what changed rather than repeating a human-completed action. Operators receive supported controls, not arbitrary native browser control. Human-assisted discovery trajectories remain evidence but are **not automatically compiled**; explicit review/approval would be required, and that approval workflow is intentionally out of scope.

[Next: multi-tenant reuse and health](05_multitenant_and_health.md) · [All five proofs](../README.md)
