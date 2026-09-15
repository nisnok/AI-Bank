# Deterministic replay internals

Public demo commands now write organized bundles under `evidence/runs/<run-id>/`; see [evidence generation](evidence.md). Proof links below point to retained runs; original provenance is unchanged.

## Files and boundaries

```text
capabilities/get_member_balance.json    Reviewed example artifact
examples/member_portal.html            Synthetic local legacy UI
examples/run_demo.py                   Browser demo entry point
src/deterministic_ui/
  models.py                           Portable artifact and result types
  surface.py                          Provider-independent UI contract
  playwright_surface.py               Async browser implementation
  resolver.py                         Ordered semantic locator resolution
  conditions.py                       Semantic checkpoints and outcome detection
  policy.py                           Configurable safety decisions
  templates.py                        Typed values and simple input substitution
  evidence.py                         Allowlisted JSON / JSONL evidence
  replay.py                           Deterministic orchestration
 tests/                               Fake-based and browser contract tests
```

Dependency direction:

```text
ReplayEngine ──> LocatorResolver ──> Surface ──> domain models
      ├───────> ConditionEvaluator ──> LocatorResolver
      ├───────> PolicyEngine ──> domain models
      ├───────> EvidenceWriter ──> Surface + domain models
      └───────> templates ──> domain models

PlaywrightSurface implements Surface and imports Playwright.
Domain models import only Python's standard library and Pydantic.
```

`Surface` is the UI port: query semantic strategies, observe, click, fill, extract, wait, and capture privacy-safe screenshots. It returns opaque `TargetRef` handles and typed observations. A desktop implementation can implement the same contract without changing replay. `PlaywrightSurface.open()` owns the browser lifecycle and exposes no browser object. Handles pin the resolved element: removal causes failure, never an automatic retarget.

`CapabilityArtifact` describes intent, input/output types, ordered actions, checks, known outcomes, compatibility, and safety. Unknown fields, unsupported versions/actions, malformed templates, duplicate IDs, undeclared outputs, and unbounded/undeclared retries are rejected. Strategies use exact names/text; relative targets mean a named role inside a uniquely resolved semantic container. CSS is allowed only after semantic strategies. A decimal is an exact finite `Decimal`, never a float. Extracted values must be plain decimal strings; currency/locale parsing is intentionally not guessed.

`LocatorResolver` tries strategies in order. Zero matches permit fallback. Multiple visible matches or an ambiguous relative container immediately return `AMBIGUOUS_TARGET`; no later fallback can override that ambiguity. Quality tiers (`semantic`, `structural`, `css_fallback`) describe resolution methods, not probabilities. Every attempt and successful strategy index are recorded, so future monitoring can measure fallback use without blocking a safe resolution.

`PolicyEngine` checks manual artifact approval or generated validation provenance, the artifact risk ceiling, and configurable risk decisions. Defaults allow reads and reversible writes, require human review for sensitive actions, and block irreversible actions. Missing configuration blocks. DRAFT artifacts require an explicit, scoped validation policy; ordinary replay rejects them. VALIDATED generated artifacts permit reads/reversible writes under the existing risk gate. Risk labels, lifecycle provenance, and the approval flag are assertions of a trusted, reviewed artifact; this prototype does not authenticate an approver or prove that a UI button is actually read-only.

`ReplayEngine.execute(artifact, inputs)` validates inputs once before any action, then processes precondition, resolution, policy, action, postcondition, output validation, and evidence. Success also requires the final checkpoint. The engine serializes its own runs; do not share a Surface between independent engines. Each attempt has a wall-clock timeout. Only recoverable failures are retried, within the artifact's bounds and only with an explicit `safe_to_repeat` declaration. A timeout can occur after an action took effect; the example never retries the Search click. Uncertain irreversible operations are verified before continuation and never blindly retried, even if marked repeatable.

`ConditionEvaluator` polls semantic conditions and known business outcomes under the same deadline. Outcomes take precedence over generic success markers. Ambiguous conditions require a human. A wait step uses this evaluator so it can recognize business outcomes while waiting; Surface also offers a direct wait operation for provider clients.

Condition expectations also accept `{{ inputs.member_id }}` references. `bind_conditions` substitutes validated inputs into a run-local copy; the stored artifact and evidence never receive the bound values. This allows the simulator capabilities to verify record identity, not just the presence of a result panel.

`EvidenceWriter` creates `evidence/runs/<bundle-id>/replay/raw/<run_id>/{metadata.json,events.jsonl,result.json,screenshots/}`. Events include run/step IDs, mode, actor, strategy attempts, match counts, quality, policy decisions, timings, retries, and status. It writes no runtime input/output values, UI text, exception messages, selectors, or templates. Typed outputs are returned in memory; persisted `result.json` deliberately has an empty outputs map. Simulator screenshots selectively mask sensitive fields before capture; unknown pages fall back to full masking. Per-image JSON manifests record coverage and fallback reasons. Screenshot failure records `CAPTURE_UNAVAILABLE` without invalidating an otherwise successful operation. Failure to write required evidence stops execution; if storage itself is unavailable, a structured `EVIDENCE_UNAVAILABLE` result is returned and complete evidence cannot be guaranteed.

## Result semantics

| Status | Example | What follows |
|---|---|---|
| `SUCCESS` | Balance extracted and final checkpoint passed | Return typed outputs |
| `BUSINESS_OUTCOME` | `MEMBER_NOT_FOUND` | Return business code, no exception |
| `RECOVERABLE_ERROR` | UI/checkpoint timeout | Inspect state; retry only when safe |
| `HUMAN_REQUIRED` | Ambiguous target or approval required | Stop for operator review |
| `HARD_FAILURE` | No target, invalid input/output, blocked policy | Correct the problem before a new run |

Failures contain run/step IDs, a code, expected condition ID, a redacted observed-state classification, retryability, safe next action, and evidence references. Normal runtime outcomes are structured results. Invalid artifact loading raises Pydantic validation errors before a run; do not log those raw validation errors because Pydantic may include supplied values.

## Boundary verification

`tests/test_boundaries.py` recursively follows local imports from replay and checks an explicit standard-library/Pydantic allowlist. It also verifies that artifact models depend only on the standard library and Pydantic, and that only `playwright_surface.py` imports Playwright. The `deterministic_ui` package has no model SDKs or LLM calls. Gemini calls live exclusively in the separate discovery provider implementation; discovery tests also enforce this separation.

## Deterministic replay limits

- This is an in-process executor for trusted artifacts and an already authorized UI session. Artifact signing, production approval/authentication workflows, and real legacy application qualification are not implemented. The browser adapter now enforces an exact-origin allowlist for the local demo. Application/version metadata is descriptive; Surface contract version and required features are enforced.
- The adapter covers the current page and uniquely scoped descendants. Multi-window workflows, special iframe bindings, and desktop support are not implemented. Exact matching and plain decimal extraction are conservative.
- Selective redaction is limited to the trusted simulator privacy profile. Other applications need their own reviewed coverage contract and otherwise use full masking. Artifact identifiers and condition IDs must themselves contain no secrets. Runtime values are excluded regardless of `sensitive` metadata.
- JSONL writes are synchronous, append-only within a run, and permission-restricted; no crash recovery or durable transaction is promised. Process termination/cancellation can leave incomplete evidence. Failed operations may already have affected the UI.
- Repeated condition checks can create many locator events/handles until the step ends. For long-running sessions, review handle lifecycle and polling volume. Full run output payloads are intentionally not persisted.
- Artifacts must describe the expected initial UI state and use preconditions where required. Stale business markers or a stale details panel can misclassify a run unless the workflow clears them or checks member identity. The local demo clears results on input. Review record-identity checkpoints carefully before using a real financial application.
- The compiler supports a narrow verified member-balance workflow. Broader compilation still requires review of risk assignment, retry idempotency, identity checks, UI mutation races, cancellation, privacy, and Surface ownership. See the compiler guide for current limits. Future health signals should not turn successful fallbacks into automatic failures.
