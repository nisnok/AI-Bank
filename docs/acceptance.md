# Acceptance verification and security audit

Executed against the real local simulator and Chromium on 2026-09-13 UTC. This pass hardens the existing architecture; ReplayEngine remains deterministic and model-free.

**Headline proof:** real Gemini discovery completed in four calls, compiled from that actual trajectory, and validated a different member in a fresh process with no model credentials or model imports. The expected identity and balance were checked in memory; persisted outputs contain no values.

[Curated evidence index](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/README.md) · [Final reviewed claims](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reviewed-report.json) · [Independent evidence assertions](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/independent-checks.json)

## Reproduce

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_acceptance.py
# Opt in to actual Gemini calls (GEMINI_API_KEY in environment or ignored .env):
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_acceptance.py --live-discovery
```

The default command never substitutes a mock for Gemini: discovery and its dependent fresh-compilation claims are SKIPPED_WITH_REASON. The opt-in command also skips if the key is absent. Provider failures are FAIL, with dependent checks skipped. Ordinary browser tests use deterministic proposals to test schema/policy containment; those are not counted as real discovery.

Individual commands below use `.venv/bin/python examples/<command>`. The two `accept_*.py` commands require a fresh `--evidence-root <directory>`; the complete commands used are preserved in the JSON reports. All runners bound execution and preserve source evidence.

## Core claims

| Claim | Command | Expected result | Evidence | Status |
|---|---|---|---|---|
| A. Real discovery | `accept_discovery.py` | Gemini chooses structured actions and verifies balance | [Real trajectory/result](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/live-retry/discovery/eabe5b06931b4f8cba2266ef8ae1ccfb/result.json) | PASS |
| B. Compilation | `accept_discovery.py` | Actual successful trajectory → parameterized immutable DRAFT | [DRAFT](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/live-retry/artifacts/get_member_balance/1.0.0/draft.json) | PASS |
| C. Zero-LLM replay | `accept_discovery.py` | Different member; identity/balance correct; credentials absent; model imports blocked; zero calls | [Validation result](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/live-retry/validation/33f1407521cc4aec9dc205106d43d013/result.json) | PASS |
| D. Business outcome | `accept_discovery.py` | BUSINESS_OUTCOME / MEMBER_NOT_FOUND; no infrastructure failure | [Business result](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/live-retry/business/de9ca6c7d970452da70317f8c5fdd68d/result.json) | PASS |
| E. Recovery | `accept_recovery.py` | One safe wait retry; search submitted once; structured RECOVERABLE_ERROR | [Recovery assertions](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/recovery/report.json) | PASS |
| F. Ambiguity | `replay_tenant.py --all` | HUMAN_REQUIRED; zero ambiguous search submissions | [Tenant scenarios](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json) | PASS |
| G. Human handoff | `run_handoff.py --scripted` | Same live session; two ownership cycles; fresh checkpoints; irreversible confirmation once | [Control summary](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/handoff/cf9eee0ef2d84e818f359364ba36ac54/control-summary.json) | PASS |
| H. Multi-tenant reuse | `replay_tenant.py --all` | Bank A/B succeed using one canonical version; zero model calls; binding semantics preserved | [Shared artifact evidence](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json) | PASS |
| I. Drift | `replay_tenant.py --all` | Unique fallback succeeds; ambiguous drift stops safely | [Evaluation metrics](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/evals/c812dfc3de4c41248f5f6c279a228b2a/summary.json) | PASS |
| J. Health | `run_reliability_eval.py` | 15 successful runs; Bank A HEALTHY; Bank B DEGRADED from fallback telemetry | [Derived health](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/health/7cdb05d231234f6ea4403167cb1de13c/derived/successful_drift/get_member_balance/1.0.0/6677c3630ef84d5c9ed29e9d4f88dd3e/summary.json) | PASS |

All ten core claims passed. The first real-provider attempt received HTTP 503 responses and did not complete. Its FAIL and downstream skips are retained in `report.json` and `live/`; one fresh bounded attempt in `live-retry/` passed all four dependent checks. The reviewed report retains both attempts rather than rewriting a failed run.

## Tests and evaluation

- Final combined suite: **244 passed** (97.20 seconds), including all 36 browser tests.
- Normal suite: 208 passed, 36 browser tests skipped by default.
- Opt-in browser suite: 36 passed, including five new browser security tests.
- Pyright: zero errors and warnings.
- Automated evaluation: all 13 expectations matched; five successful reads, one valid business outcome, six terminal failures, one human stop. Completion 46.2%, primary resolution 91.3%, fallback usage 8.7%, fallback recovery 40%, human intervention 7.7%, seven drift events. The injected-fault mix is not a production reliability estimate.
- Secret-shape and current-credential matching found no credential leaks in repository text. Fictional PII/secret canary scans passed over newly generated evidence, including numeric business values. Matched values are never printed. These are bounded scans, not a general DLP guarantee.

Re-run the bounded text scan with:

```sh
.venv/bin/python -m acceptance.privacy --repository --evidence evidence/acceptance-local/<run-id>
```

## Screenshot policy and inspection

`PlaywrightSurface.open(..., screenshot_policy=ScreenshotPolicy.SELECTIVE_REDACTION)` is the default. `FULL_MASK` and `DISABLED` remain explicit options. The trusted simulator declares a capture-only privacy profile and workflow state; capability locators do not use these annotations. Required categories must be present for sensitive states. All inputs, table values, marked sensitive fields, and embedded content are masked. Labels, headings, branding, buttons, loading notices, and modal/workflow structure remain visible. The reference iframe is conservatively masked.

Chromium applies masks before image encoding. Screenshot calls receive no disk path; only the safe bytes are written. The adapter compares inventories and DOM structure before/after selective capture, discards uncertified in-memory bytes, and captures FULL_MASK if coverage or stability cannot be established. Each evidence image has a `.png.json` manifest with policy, category/count, and fallback reason; it contains no masked values. DISABLED produces a manifest/event and no image.

Pixel tests verify solid masks over member/name/balance/account/deposit/password/token fields, while heading pixels remain non-uniform. Inspection of representative account-opened and balance screens confirms useful layout and hidden values. Application screenshots show the workflow/modal state; ownership is recorded in the associated handoff events, not claimed as native-browser gesture capture.

Some historical images remain fully black because they predate this policy. Two captures in the initial current acceptance run also used the conservative full-mask fallback when a stable selective capture could not be certified; the manifests explicitly say REDACTION_FALLBACK_FULL_MASK. Representative final balance and account-opening screenshots are selective, not fully black. Both actual black fallback examples are retained for review.

## Evidence selection

The final submission selection is `evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/`. It retains the real discovery/compilation/validation pipeline, recovery and handoff traces, aggregate evaluation/tenant/health reports, a few representative raw runs, and 16 representative screenshots. Bulk runs remain under ignored `evidence/acceptance-local/8488062ae9bc4e31b821e6a9ae4d8793/`. No historically committed evidence was deleted or rewritten. Existing documentation references were inventoried before changing ignore rules.

The archive manifest gives SHA-256 hashes and maps original paths to copied files. Source JSON is preserved byte-for-byte, so original evidence references still name the local root; use the archive mapping for retained copies. Unselected raw stress runs can be regenerated with the recorded commands; their aggregate metrics, source IDs, and digests remain in the reports.

## Security guardrails verified

| Guardrail | Finding / action | Verification |
|---|---|---|
| Origin restriction | Added exact scheme/host/port allowlist. Loopback defaults; file demos pin one file URL. Context-wide routing blocks off-origin navigation, redirects, frames, popups, and fetches. Service workers/downloads disabled; WebSockets blocked. | Allowed local navigation and blocked external/redirect browser tests. |
| Screenshot privacy | Replaced unconditional black screenshots with certified simulator masking and fail-closed fallback. | Pixel assertions, manifests, no-path capture assertions, manual image inspection. |
| Goal privacy | Free-form discovery goals could retain nonnumeric private text. Replaced persisted goal with fixed redacted workflow description. | Secret-canary discovery test and generated evidence scans. |
| Model action boundary | Existing typed operations already reject scripts, shell commands, URLs, literal inputs, CSS/XPath, and model-supplied policy fields. No new execution route added. | Schema rejection tests plus real-browser adversarial proposal. |
| Prompt injection | Malicious-looking simulator text is observation data; an attempted Transfer All Funds proposal is blocked by authoritative unreviewed-risk policy before dispatch. | HUMAN_REQUIRED, attempted=false, server mutation counters zero. Not universal immunity. |
| Policy integrity | Existing draft validation, binding restrictions, and reliability policy preserve safety. | Prior tests verify draft cannot self-approve, bindings cannot change semantics, degraded health cannot weaken BLOCK/REQUIRE_HUMAN. |
| Ownership and mutation | Existing controller blocks automation during HUMAN ownership; irreversible uncertainty verifies instead of blind retry. | Browser takeover tests, retained ownership counts, fresh resume checkpoints, one confirmation/account. |
| Model-free replay | Existing transitive dependency checks retained; fresh validation worker blocks model modules and removes model credentials. | Import graph tests and actual different-member validation. |

Configure additional trusted origins explicitly with `allowed_origins=frozenset({"http://127.0.0.1:8765"})`. Entries are exact origins, not URL prefixes. An off-origin request taints the session and subsequent Surface interactions fail closed. This is a trusted local demo boundary, not browser-process sandboxing.

## Known limitations

- Handoff uses a bounded mediated operator panel and a clearly labeled scripted acceptance driver, not arbitrary native-browser action capture.
- Resume/control state is in memory; no durable cross-process recovery.
- Authentication is local/minimal; artifacts and application markup are trusted, not cryptographically authenticated.
- Selective redaction is a reviewed simulator contract, not automatic PII discovery. Unknown applications require a new reviewed profile or use FULL_MASK. Fully masking embedded content trades detail for privacy.
- Typed actions and policy contain the tested injection attempt; a malicious application that misrepresents a safe control is outside this proof. No universal prompt-injection immunity is claimed.
- Desktop automation remains an abstraction without an implementation.
- Provider availability and browser timing remain variable. Live discovery can fail independently of deterministic replay, as the retained 503 attempt demonstrates.
- Replay tests and stress evaluation demonstrate bounded scenarios, not statistical production reliability or authorization for real financial transactions.
