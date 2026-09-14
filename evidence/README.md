# Five-minute evidence walkthrough

If you have five minutes, inspect these five proofs in order.

1. [Real Gemini discovery](reviewer/01_real_discovery.md)
2. [Compiled capability](reviewer/02_compiled_capability.md)
3. [Different-input zero-LLM replay](reviewer/03_zero_llm_replay.md)
4. [Failure handling + human handoff](reviewer/04_failure_and_handoff.md)
5. [Multi-tenant reuse + drift + health](reviewer/05_multitenant_and_health.md)

**Primary reviewer run:** `key-retry-20260914-1`. This is the latest retained successful real-Gemini discovery → compilation → different-input replay pipeline. Proofs 1–3 follow that one run. Proofs 4–5 use supporting / historical evidence for distinct fault, handoff and tenant-health scenarios. The older canonical tenant artifact keeps its original provenance.

## Additional / audit evidence

These are supporting records for deeper inspection, not additional steps in the primary walkthrough.

- [Primary run report and source/hash map](acceptance/key-retry-20260914-1/README.md).
- Supporting / historical archives: [recovery, tenants, health and replay handoff](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/README.md); [discovery handoff and earlier live pipeline](acceptance/ca89e14b3e69427a87b8360d73f527e0/README.md).
- [Automated evaluation](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/evals/c812dfc3de4c41248f5f6c279a228b2a/summary.json): 13 controlled scenarios; see [methodology](../docs/evaluation.md).
- [Selective screenshot manifest](acceptance/key-retry-20260914-1/validation/a7e113edc24045959dd31b58116d18a2/screenshots/final.png.json) and [privacy policy](../docs/acceptance.md#screenshot-privacy).
- [FULL_MASK fallback manifest](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/search_member.png.json): the adjacent black image demonstrates only fail-closed privacy, not a usable workflow view.
- [Initial provider failure](acceptance/cleanup-live-failure/report.json) and [verification summary with successful follow-up](acceptance/cleanup-verification.json): failures remain visible rather than being replaced with success.
- [Recorded privacy/integrity checks](acceptance/cleanup-checks.json) and [acceptance reproduction commands](../docs/acceptance.md#reproduce). Check counts describe that recorded pass, not subsequent documentation edits.

Raw JSON/logs remain the source of truth. Archive manifests map original ignored local paths to retained copies; unselected original captures are not promised in a fresh clone. No raw records were rewritten or moved for this walkthrough. New runtime output stays in ignored `acceptance-local/`.
