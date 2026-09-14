# Assignment evidence

Start with the table below. These are selected **real execution records**, not hand-written success fixtures. Gemini decisions are real where marked; acceptance human actions are explicitly scripted operator inputs, not a claim of physical human participation.

| Assignment claim | Best evidence | What it proves |
|---|---|---|
| Real Gemini discovery and successful trajectory | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live/discovery/0d722350416e48fd8c73cf92ff66bf55/result.json) | Actual four-call provider run; adjacent trajectory-*.json files contain the redacted verified steps. |
| Compiled/versioned capability | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live/artifacts/get_member_balance/1.0.0/draft.json) | DRAFT generated from that actual successful run; canonical reusable version is linked below. |
| Different-input replay and zero model calls | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live/report.json) | Fresh worker checks changed input, correct identity/balance, absent credentials and blocked model imports. |
| Business outcome | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live/business/1997d773741e47c387de77f39e14ad94/result.json) | BUSINESS_OUTCOME / MEMBER_NOT_FOUND, with zero model calls. |
| Recoverable failure | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/recovery/report.json) | Bounded wait retry; one search submission, structured RECOVERABLE_ERROR. |
| Ambiguity fails closed; multi-tenant reuse; UI drift/fallback | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json) | Same canonical capability on both tenants; unique fallback succeeds, ambiguous search is never submitted. |
| Discovery-time human handoff | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live-handoff/011a662b0bed41a498c245a379aed91e/report.json) | Real Gemini decisions, scripted operator, same session, one acknowledgement, verified continuation. |
| Replay human handoff and session preservation | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/control-summary.json) | Two ownership cycles; zero automation actions during HUMAN; one account confirmation. |
| Human action audit | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/human-action-1.json) | Actor/source, semantic action, before/after state and verified checkpoints; adjacent events.jsonl gives the timeline. |
| Capability health | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/health/7cdb05d231234f6ea4403167cb1de13c/derived/successful_drift/get_member_balance/1.0.0/6677c3630ef84d5c9ed29e9d4f88dd3e/summary.json) | 15 successful runs: Bank A HEALTHY, Bank B DEGRADED from fallback use; controlled evidence only. |
| Automated evaluation | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/evals/c812dfc3de4c41248f5f6c279a228b2a/summary.json) | 13 injected scenarios, all expectations matched; 46.2% completion is an adverse-scenario metric. |
| Selective screenshot redaction | [Open record](acceptance/ca89e14b3e69427a87b8360d73f527e0/live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handoff_1.png) | Readable supervisor notice/layout with sensitive values masked; adjacent .png.json documents coverage. |
| Fail-closed screenshot behavior | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/search_member.png.json) | fallback_full_mask=true. Adjacent image is intentionally opaque because selective capture could not be certified. |
| Honest provider failure | [Open record](acceptance/8488062ae9bc4e31b821e6a9ae4d8793/live/discovery/378ac3811fb447f8b82b9bed3c362e2a/result.json) | Retained actual failed provider run; a separate fresh attempt succeeded. |

## Latest successful pipeline

[Open the latest real Gemini evidence](acceptance/key-retry-20260914-1/README.md): six discovery calls including retries, compiled/versioned artifact, different-input replay with zero model calls, and MEMBER_NOT_FOUND. The run used the updated local credential; no credential value is persisted.

## Artifact provenance

The unchanged [canonical VALIDATED capability](../capabilities/generated/get_member_balance/1.0.0/validated.json), its [DRAFT](../capabilities/generated/get_member_balance/1.0.0/draft.json), and [validation record](../capabilities/generated/get_member_balance/1.0.0/validations/c0a8057c3d2b40bb95d380807c51c33a.json) remain the exact artifacts used by tenant reuse. The original compilation, validation and generated-replay text records remain under their original directories. The original discovery source is local-only; the table links a separately retained real discovery-to-compilation proof. Historical opaque screenshots are omitted while their original references remain in unchanged logs.

## Structure and selection

```text
evidence/
  README.md
  acceptance/
    cleanup-verification.json  latest actual verification summary
    cleanup-live-failure/      initial failed provider attempt
    key-retry-20260914-1/      latest successful real Gemini pipeline
    8488062.../     recovery, replay handoff, tenants, health, evaluation, privacy
    ca89e14.../     real discovery/compilation/replay and discovery handoff
  compilation/     original canonical compilation provenance (text)
  validation/      original canonical validation provenance (text)
  generated-replay/ original canonical business-outcome replay (text)
```

The two archive README files describe their selected captures and omissions. Raw records and retained screenshots are unchanged; archive manifests preserve original hashes and map ignored source paths to retained copies. Aggregate reports containing machine-specific absolute paths are excluded, not rewritten. Only selected raw runs are included for repeated evaluation/health traffic; source references to unselected runs are provenance, not clone-relative promises.

Bulk new output, cache files and historical duplicates remain ignored/local. Reproduce checks using [acceptance commands](../docs/acceptance.md); see the [final cleanup review](../docs/cleanup.md) for current results. No successful evidence was fabricated or edited during cleanup.

Latest verification: the [successful real Gemini retry](acceptance/key-retry-20260914-1/README.md) passed discovery, compilation, different-input zero-model replay and the business-outcome check. The [summary](acceptance/cleanup-verification.json) preserves both attempts; the [initial provider failure](acceptance/cleanup-live-failure/report.json) remains unchanged.
