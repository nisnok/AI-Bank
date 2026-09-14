# Final submission cleanup review

Cleanup changes documentation, evidence selection and ignore rules only. Existing uncommitted implementation work is preserved. No source architecture, fixtures, canonical capability bytes or tenant bindings were changed by this pass. Nothing was committed or pushed.

## Inventory and decisions

The initial inventory contained 938 tracked files plus local runs and the uncommitted completion pass. All source/test/config files, docs, examples, tracked evidence, root entries and documentation references were reviewed before removal.

| Class | Decision |
|---|---|
| A — required source/test/config | Keep src, tests, examples, pyproject, reviewed capabilities and tenant bindings. Keep portable VS Code settings because they configure the interpreter/import path and ignored env injection. |
| B — reviewer documentation | Rewrite the root README, keep the seven-heading REPORT, retain technical guides, add the evidence entry point. |
| C — unique proof | Keep two complementary curated archives and original canonical compilation/validation/business provenance. Restore twelve small terminal JSON records referenced by curated indexes. |
| D — runtime/cache/local | Ignore virtualenv, browser binaries, Python/test/build caches, env files, editor noise, logs, runtime evidence and generated health. |
| E — redundant development artifacts | Remove older loose demo, tenant, handoff, evaluation and reliability evidence from submission after mapping claims to retained proof. Preserve originals in an ignored local backup. |

Removed from the submission: 608 previously tracked files and two untracked completion aggregate reports (610 local files moved). This includes old `evidence/evals`, `evidence/reliability`, `evidence/tenants`, `evidence/tenant-demos`, `evidence/handoff`, five loose demo-run directories, generated `health`, seven opaque legacy screenshots, and six aggregate reports with machine-specific command paths. Raw successful records were not edited. The backup stays local under ignored `evidence/acceptance-local/cleanup-backup`.

The two curated archives are retained for complementary claims: the first covers recovery, replay takeover, tenancy, drift, health, evaluation and privacy; the second covers real discovery takeover and a fresh unassisted Gemini compilation/replay pipeline. The original canonical artifact's provenance remains at its original paths. Duplicate runtime health snapshots are reproducible from evidence. Two intentional FULL_MASK examples remain with explicit explanations; 23 other selected screenshots preserve readable UI with sensitive regions masked.

## Documentation and references

README now puts the architecture diagram, setup, deterministic demo, real discovery, acceptance and tests first. Detailed replay internals moved into `docs/replay.md`. REPORT keeps exactly the assignment's seven headings and states all requested cuts. Discovery documentation describes interactive pause/ownership/action/handback/fresh observation/resume and the unimplemented human-assisted compilation approval workflow.

Fixed the simulator startup command (the server is `python -m bank_simulator.server --port 8765`, not the replay CLI), stale claims that health was unimplemented, the discovery `--headed` command missing `--non-interactive`, historical run references superseded by curated proofs, and twelve already-broken curated scenario links. Original source JSON references to unselected/local runs remain provenance, not promises that every original capture ships in a clone. Archive maps document selected copies; six omitted aggregate entries are explicitly listed. Retained manifest hashes are verified without rewriting source records.

## Final verification

The [derived verification summary](../evidence/acceptance/cleanup-verification.json) records the actual final runner results. It is a summary of source output, not a fabricated raw execution record.

| Check | Actual result |
|---|---|
| Normal tests | 215 passed; 37 browser tests skipped |
| Separate browser suite | 37 passed |
| Type checks | PASS, zero errors |
| Controlled evaluation | PASS, all 13 expectations |
| Tenant reuse, drift and ambiguity | PASS |
| Health | PASS, 15 successful runs; Bank A HEALTHY / Bank B DEGRADED |
| Replay and scripted discovery handoff | PASS |
| Bounded recovery | PASS |
| Independent saved-evidence assertions | PASS |
| New acceptance evidence privacy | PASS |
| Initial cleanup live Gemini discovery | FAIL: HTTP 503, HTTP 429, then connection error |
| Initial dependent live checks | SKIPPED because initial discovery failed |
| Subsequent live pipeline retry | PASS: real Gemini discovery (6 calls including retries), compilation, different-input zero-model replay, and business outcome |

The [initial failed provider trace](../evidence/acceptance/cleanup-live-failure/events.jsonl) remains unchanged. The original full live-enabled acceptance command exited 1; all non-provider checks passed. After the local credential update, a separate [live pipeline retry](../evidence/acceptance/key-retry-20260914-1/README.md) passed all four provider-dependent claims. This is a successful follow-up, not a rewritten initial run or a claim that the full suite was rerun. Its source records are now retained byte-for-byte with hashes and one representative selective screenshot.

Repository and retained evidence text pass credential/current-key and fictional-PII checks. Intentional fictional data in fixtures and documentation is retained. No env files or machine-specific absolute paths appear in the proposed submission files. These checks cover the working-tree submission, not historical Git objects. Selected screenshot manifests and browser pixel tests support privacy; representative selective and fallback captures were inspected. Documentation/link and final integrity results are recorded in [cleanup checks](../evidence/acceptance/cleanup-checks.json).

## Remaining limits and readiness

The repository is organized for submission and backed by retained real-run evidence. The latest live pipeline retry passed, and the earlier failure remains disclosed; future live demos still depend on provider availability/quota. Scope remains a fictional local simulator, bounded mediated human actions, no arbitrary native takeover, no human-assisted compilation approval workflow, in-memory resume, no desktop implementation, and no universal prompt-injection or production-reliability guarantee.

Review the working-tree diff before the final commit. No commit or push was performed.
