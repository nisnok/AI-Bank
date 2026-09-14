# canonical capability reuse and controlled UI drift

## Reviewer commands

Use the existing dependencies and Chromium installation. No Gemini key is required.

```sh
# All seven real-browser scenarios and a generated evidence index:
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --all

# Individual scenarios:
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --tenant bank_a
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --tenant bank_b
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --tenant bank_b --drift label
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --tenant bank_b --drift structural
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/replay_tenant.py --tenant bank_b --drift ambiguous
```

The default runtime member is 83921. Use `--member-id 99999` for MEMBER_NOT_FOUND or `--application-version 2` to demonstrate incompatible application rejection. The CLI treats an expected negative scenario as a successful demonstration; the actual execution status remains in RunResult and evidence.

Every scenario loads the same actual Bank A-discovered artifact:

`capabilities/generated/get_member_balance/1.0.0/validated.json`

Its discovery provenance points to real Gemini run `6234bdefa80947b8856fbc677939560c`. The tenant demo does not call discovery or the compiler. There is no copied Bank B capability. Each scenario gets its own isolated application session; cross-tenant reuse means reuse of the canonical workflow, not sharing customer-session cookies.

## Binding contract

```text
Canonical CapabilityArtifact + TenantContext + TenantBinding
                         + observed application identity
                                      ↓
                         TenantBindingResolver.bind()
                                      ↓
                     in-memory EffectiveCapability
                                      ↓
                               ReplayEngine
```

`TenantContext` declares tenant ID, display name, local application URL, product, and expected application version. These fields remain separate from CapabilityArtifact.

`TenantBinding` declares tenant ID, binding version, canonical capability ID/version and digest, product/application version, and a list of locator overrides. An override matches an entire canonical SemanticTarget and replaces only its strategy ladder. Matching the full target is important because discovered concepts such as `observed_0` can recur for different elements.

Bindings:

- `tenant_bindings/bank_a/1.0.0.json`: explicit baseline binding, no locator changes.
- `tenant_bindings/bank_b/1.0.0.json`: five target mappings for input, search, balance, displayed identity, and missing-customer message.

The binder applies a matching target mapping consistently to action targets, preconditions, postconditions, final success, and business-outcome conditions. It preserves target concepts and condition expectations. Template substitution still happens only during ordinary run-local replay.

Strict validation rejects unknown fields, unknown/duplicate target mappings, mismatched tenant or capability identity, changed canonical digests, incompatible product/version, unordered/duplicate locator strategies, changed semantic roles, CSS-only replacement of semantic targets, and strategies outside the canonical required-feature contract.

Bindings cannot contain action types, step ordering, inputs, outputs, risk levels, retry policy, approval flags, lifecycle changes, or altered success predicates. A protected-field comparison also verifies that the produced artifact differs only in target strategies. Policy is still evaluated normally; a binding cannot promote a DRAFT or grant approval.

The effective artifact exists only in memory. Its ID/version, typed contracts, risk, safety, lifecycle, and original discovery provenance remain the canonical values. The canonical VALIDATED lifecycle describes the original artifact; tenant-specific execution evidence records validation of the binding separately. It does not pretend Bank B was the source of the original discovery.

Bindings are trusted, reviewed configuration: structural validation cannot prove that an arbitrary label or selector identifies the intended real-world business operation. Treat changes to locator mappings as reviewable changes, pin them to a canonical digest, and use a new binding version for changes. This prototype does not sign files or implement an approval service.

## Bank B and drift are separate

The simulator stores tenant and drift independently in each Session. Both tenants use the same member data and domain transitions.

| Aspect | Bank A | Bank B |
|---|---|---|
| Branding | Northstar Example Credit Union | Harbor Bank B |
| Input label | Member ID | Customer Number |
| Input ID | member-key | customer-reference |
| Search control | Search | Find Customer |
| Balance label | Savings balance | Available Savings |
| Identity label | Loaded member identifier | Loaded customer identifier |
| Negative message | Member not found | Customer not found |
| Structure | Basic lookup form | Fieldset/nested lookup and record wrappers |

Independent drift modes:

- **label:** Customer Number becomes Customer #. Accessibility and label strategies no longer match. The already configured, baseline-valid `#customer-reference` fallback resolves uniquely at depth 2. Replay continues.
- **structural:** adds nested containers around the input while preserving labels and semantics. Semantic resolution still succeeds; no fallback signal is invented merely because a wrapper changed.
- **ambiguous:** adds a second matching Find Customer control. Resolution returns AMBIGUOUS_TARGET at the precondition and stops before any search submission.

Fallback CSS is not synthesized after drift and the binding is not changed to make the drift run pass. All Bank B modes use the same binding file/digest.

## Compatibility and model isolation

Before any workflow action, the tenant runner reads three visible semantic status fields through Surface: institution identifier, application product, and application version. It rejects missing/ambiguous identity or incompatible values. Compatibility failures produce structured HARD_FAILURE evidence and perform no fill/click. Version negotiation and frame traversal are deliberately unsupported.

The simulator contract product is `legacy-bank-simulator`, version `1`. Version `2` is an explicit incompatibility fixture. Current metadata records expected product, observed product/tenant/version, canonical digest, binding digest/version, and tenant identity. URLs and runtime values are not persisted.

ReplayEngine only gains an optional evidence context. It contains no bank-specific conditions and imports no tenant-binding implementation. TenantBindingResolver and the tenant runner use domain models and Surface; neither needs Playwright or a model client.

The CLI installs an import guard against discovery/provider modules before loading the replay path and removes common model credentials from its process environment. It checks that no blocked module loaded. Static dependency tests preserve ReplayEngine's transitive standard-library/Pydantic boundary. These checks support the zero-call evidence; they are not an operating-system network firewall.

## Locator telemetry

The existing EvidenceWriter records typed LocatorTelemetry per resolution, including condition checks:

- canonical capability ID/version, tenant ID, binding version, run ID, timestamp;
- step and optional condition ID;
- expected primary strategy, whether it succeeded, strategy used/last attempted;
- fallback depth, match count, resolution quality, ambiguity;
- whether fallback/retry recovery was needed;
- actual step result and eventual run result.

`locator-telemetry.json` contains all resolution observations plus typed DriftSignal entries for successful fallback or ambiguity. A final checkpoint can have no step ID. Polling can generate multiple observations; they are retained rather than collapsed into a fabricated score.

Quality uses the existing resolver categories: semantic, structural, css_fallback, unresolved. A fallback remains successful when its target is unique. The engine does not automatically disable, degrade, rewrite, or fail a capability because a fallback was used.

A signal indicates a changed resolution path or ambiguity; it does not by itself establish the cause. Structural changes that preserve semantic resolution may produce no drift signal. The separate health layer aggregates these signals; no interactive reliability dashboard is implemented.

## Actual acceptance evidence

The [retained seven-scenario browser report](../evidence/acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json) covers Bank A/B baselines, label and structural drift, ambiguity, a missing member, and an incompatible version. All use one canonical artifact digest and zero model calls. Unique fallback succeeds; ambiguity records zero search submissions. Selected raw telemetry and result bundles are retained next to the report; bulk traces are local-only.

Browser tests independently verify the expected Decimal balance for the different member on both tenants. Runtime values are deliberately omitted from persisted results. The [evidence index](../evidence/README.md) links the shared artifact and identity/isolation checks.

## Verification and remaining limits

```sh
.venv/bin/pyright
.venv/bin/python -m pytest -q
RUN_BROWSER_TESTS=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python -m pytest -q
```

Tests cover both tenants, typed contracts, protected binding fields, digest/version checks, approval preservation, missing bindings, fallback signals, ambiguity without clicks, structural drift, business outcomes, observed compatibility, and the other system layers.

Current full-suite results are recorded in [acceptance](acceptance.md).

Remaining limitations are trusted unsigned locator configuration, exact version matching, file-backed evidence, simulator-specific screenshot redaction, per-resolution telemetry volume, and preflight identity that is not continuously re-attested during every UI operation. Effective capabilities are transient and there is no persistent binding-promotion/governance service. New business workflows require new capability versions.

Capability-health aggregation is implemented separately. Automatic repair, self-healing, tenant dashboards, and distributed infrastructure remain out of scope.

[Capability health](health.md) now derives explainable assessments from replay evidence. [Automated evaluation](evaluation.md) adds controlled failure scenarios separately; automatic repair/healing remains unimplemented.
