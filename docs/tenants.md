# Milestone 6: canonical capability reuse and controlled UI drift

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

A signal indicates a changed resolution path or ambiguity; it does not by itself establish the cause. Structural changes that preserve semantic resolution may produce no drift signal. No aggregate health score or reliability dashboard is implemented.

## Actual acceptance evidence

The genuine seven-scenario browser run is indexed at:

[evidence/tenant-demos/f95ba7b302414500a75301a83da87b72/README.md](../evidence/tenant-demos/f95ba7b302414500a75301a83da87b72/README.md)

| Scenario | Result | Run directory under evidence/tenants |
|---|---|---|
| Bank A baseline | SUCCESS | 0b438a1e721342aab35fa41bdc3623ef |
| Bank B baseline | SUCCESS | d96e824a8ad74f67878c7055ea3abeea |
| Bank B label drift | SUCCESS, fallback signals | cea50aab61f3487b8a50cd4898193617 |
| Bank B structural drift | SUCCESS | a11b22997ba046579eede1b007f0c194 |
| Bank B ambiguity | HUMAN_REQUIRED / AMBIGUOUS_TARGET | 2c1ab64ee52e44938c1dae0b64bac76e |
| Bank B missing member | BUSINESS_OUTCOME / MEMBER_NOT_FOUND | 9bc634bdd8994398bdee8a84db41fc90 |
| Bank B incompatible version | HARD_FAILURE / INCOMPATIBLE_APPLICATION_VERSION | f50be57402da4ee59662cb533fbc4081 |

All seven reference the same canonical digest and report zero model calls. Bank B's successful and drift runs reference the same binding file. The ambiguity scenario records zero server-observed search submissions. The generated index also records import-guard checks and submission counts; these come from execution, not hand-authored success records.

The label-drift run records primary failure, successful CSS fallback at depth 2, one match, css_fallback quality, and final SUCCESS. Its three fallback signals correspond to the input visibility check, fill target resolution, and value postcondition.

Browser tests independently assert the returned balance is Decimal("807.20") for member 83921 on both tenants and safe drift variants. Runtime balances are intentionally omitted from persisted result outputs. Screenshots retain the existing full masking.

The acceptance bundle predates the additional observed-product/tenant fields for rejected preflight runs; it has not been rewritten. New executions include those fields. The existing rejected-version record already records the actual incompatibility result.

## Verification and remaining limits

```sh
.venv/bin/pyright
.venv/bin/python -m pytest -q
RUN_BROWSER_TESTS=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python -m pytest -q
```

Tests cover both tenants, typed contracts, protected binding fields, digest/version checks, approval preservation, missing bindings, fallback signals, ambiguity without clicks, structural drift, business outcomes, observed compatibility, and all earlier milestones.

The full browser suite passed 192 tests before the final three binding-ladder tests were added. Those additional tests passed in the focused tenant suite. The requested final browser rerun was declined by the approval prompt; no newer full-browser result is claimed.

Remaining limitations are trusted unsigned locator configuration, exact version matching, file-backed evidence, full-mask screenshots, per-resolution telemetry volume, and preflight identity that is not continuously re-attested during every UI operation. Effective capabilities are transient and there is no persistent binding-promotion/governance service. New business workflows require new capability versions.

Capability-health aggregation, automatic repair, self-healing, tenant dashboards, and distributed infrastructure remain out of scope.
