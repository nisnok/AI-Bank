# Evidence

**[Current: start here](current/README.md)** — the designated fully successful acceptance run, with discovery, replay, handoff, multi-tenant and evaluation evidence.

**[Run history](runs/)** — the small, intentionally retained evidence set. Other new runs are local and ignored by Git.

**[Capabilities](../capabilities/README.md)** — the authoritative versioned automation artifacts.

## Proof at a glance

| Claim | Result in current | Evidence |
|---|---|---|
| Real Gemini discovery | PASS | [Discovery](current/discovery/README.md) |
| Compiled typed capability | PASS | [Compilation](current/replay/compilation.json) |
| Different-input zero-LLM replay | PASS; zero calls | [Replay verification](current/replay/validation.json) |
| Safe failures and human handoff | PASS; bounded audited actions | [Handoff](current/handoff/README.md) |
| Multi-tenant reuse, drift and health | PASS; healthy/degraded tenants | [Multi-tenant](current/multitenant/README.md) |
| Controlled evaluation | All 13 scenario expectations matched | [Evaluation](current/evaluation/README.md) |
| Privacy and safety | PASS in the recorded checks | [Acceptance checks](current/evaluation/acceptance.json), [privacy scan](current/evaluation/privacy-scan.json) |

Current is a relative link to the [complete imported successful run](runs/ca89e14b3e69427a87b8360d73f527e0/README.md). This direct link also works in GitHub's web viewer. Its summary identifies the source run and original execution dates. A more recent failed or partial run does not replace it. The current source can change automatically after a fully successful new acceptance run; its `source_run_id` is authoritative.

## Raw / audit trail

[Generation and promotion rules](../docs/evidence.md) explain how every future public demo/acceptance command creates a standard run bundle automatically. No manual curation is needed.

Retained history contains three distinct proofs:

- [Full acceptance](runs/ca89e14b3e69427a87b8360d73f527e0/README.md), designated current: actual discovery, compilation, different-input zero-model replay, failures, handoff, tenants, health and all 13 evaluation scenarios.
- [Canonical capability provenance](runs/6234bdefa80947b8856fbc677939560c/README.md): the original Gemini discovery and compiler/validation/business records for the authoritative `get_member_balance@1.0.0`. Historical FULL_MASK captures intentionally show the older fail-closed privacy behavior; current contains selectively redacted screenshots.
- [Real-Gemini discovery handoff](runs/011a662b0bed41a498c245a379aed91e/handoff/discovery-handoff.json): four real model calls and one explicitly scripted, bounded operator action in the same browser session.

The latter two are historical stage proofs, labeled PARTIAL because neither is a new complete acceptance execution. Raw records and capability provenance remain unchanged. Old source locations recorded inside copied evidence are historical identifiers; manifests map them to retained files.

The only compatibility path is [canonical validation](validation/c0a8057c3d2b40bb95d380807c51c33a/): a relative link preserving the three explicit evidence references in the authoritative validation artifact. It duplicates no files.

New runs remain on disk for debugging and are ignored by default. Retention is deliberate: add a chosen run ID to the `.gitignore` allowlist before committing it. If a successful run updates current, retain its target together with the pointer. Execution never automatically deletes failed runs. Superseded retries and old development histories have been deleted, not archived.

Human controls remain bounded; human-assisted discovery is not automatically compiled. Health and controlled evaluation results are not production-reliability probabilities.
