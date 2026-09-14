# Architecture

The working slice is a fictional member-balance lookup on a local banking simulator. Gemini drives a bounded observe → decide → act loop against Chromium. It sees normalized observations and returns typed decisions referring to current observation IDs. The application performs real UI interactions; neither discovery nor replay retrieves balances through a simulator API.

CapabilityCompiler consumes the successful in-memory discovery trajectory, verifies action provenance, parameterizes invocation values, and writes a versioned DRAFT. A separate process validates that artifact with a different member and no model credentials or imports. Successful validation creates a separate VALIDATED snapshot; it does not overwrite the draft. Ordinary execution uses the deterministic, model-free ReplayEngine.

Surface separates perception/actions from workflow meaning. PlaywrightSurface is the browser implementation. LocatorResolver, ConditionEvaluator, PolicyEngine, and EvidenceWriter provide targeting, verification, authorization, and evidence. HandoffManager and SessionController retain one session through human intervention. Tenant bindings specialize locators; evidence feeds local health summaries and controlled evaluation. These are in-process components with file storage: separate services would add deployment complexity without improving this demonstration.

# Artifact schema

A capability has an ID/version, typed inputs and outputs, ordered steps, semantic targets, checkpoints, known business outcomes, compatibility, safety metadata, lifecycle, and provenance. Decimal financial outputs remain Decimal values in memory rather than binary floats. The caller receives typed outputs; persisted evidence omits their values.

Each step declares its operation, risk, input/output binding, pre/postconditions, timeout, and bounded retry metadata. Targets use ordered accessibility, label, text, relative, and CSS strategies. Semantic strategies are preferred; CSS is a reviewed fallback. Ambiguity terminates resolution instead of choosing the first match. The compiler retains strategies grounded in observed successful interactions, not arbitrary model-authored selectors.

Generated artifacts start unapproved and DRAFT, with discovery run/model/compiler provenance. VALIDATED means a different-input deterministic replay passed; it is not proof of production authorization. Storage uses exclusive creation and checks workflow identity across validation. Artifacts are trusted local configuration, not cryptographically signed. Human-assisted discovery is recorded but rejected by automatic compilation pending explicit review, so manual actions cannot silently become unattended automation.

# Determinism & error handling

Replay follows the saved steps and locator ladder without LLM decisions. It validates inputs, checks preconditions, resolves targets, applies policy, acts, verifies postconditions and final identity, and returns structured results. A fresh validation worker removes model credentials, blocks model imports, and verifies a different member and expected balance. Import-graph tests enforce the model-free boundary.

BUSINESS_OUTCOME represents legitimate results such as MEMBER_NOT_FOUND. RECOVERABLE_ERROR represents bounded failures such as a slow load; HARD_FAILURE stops invalid or unsupported execution. HUMAN_REQUIRED is an explicit safety stop. Failures retain step, condition, safe diagnostic code, and evidence references.

Retries require safe_to_repeat and a fixed attempt limit. An uncertain irreversible action is verified before any continuation and is never blindly repeated. Ambiguous targets stop for human review. The automated evaluator injects 13 controlled scenarios, classifies observed failures, and reports completion, locator/fallback, intervention, and drift metrics. Expected refusals can pass an evaluation while remaining unsuccessful workflows; the stress-suite success rate is not a production reliability estimate.

# Heterogeneity & multi-tenant

The portable flow describes operations and semantic targets; Surface owns provider handles, observations, and interactions. A desktop adapter could implement that seam using OS accessibility, but none is implemented. General frameset traversal and screenshot-coordinate targeting would require additional provider capabilities and reviewed artifact semantics.

Bank A and Bank B use one canonical capability ID/version. Bindings change locator strategies only; they cannot change actions, risk, inputs/outputs, checkpoints, or approval. Tenant/product/version checks fail closed on incompatible configurations. Label drift can recover through a unique fallback; ambiguous drift stops safely.

Locator telemetry identifies fallback depth, primary success, and ambiguity per tenant. Health aggregation can classify a still-successful Bank B as DEGRADED from elevated/increasing fallback use while Bank A remains HEALTHY. Assessments retain source run IDs and configurable thresholds. Health never rewrites capabilities, and its optional risk policy can strengthen but cannot weaken existing safety decisions.

# Escalation & handoff

Policy blocks, dialogs, ambiguity, and stuck states produce intervention context. Replay and interactive discovery use the same HandoffManager pause/resume loop, operator action allowlist, and control lease. Taking control changes AUTOMATION to HUMAN; automation UI actions are rejected until handback. Human actions affect the same live browser session and are audited separately with sensitive values omitted.

Handback requires a fresh observation and trusted resume checkpoints. Replay recognizes an already-completed irreversible step instead of repeating it. Discovery discards cached outputs, obtains a fresh observation, and requests a new model decision rather than re-dispatching the blocked proposal. Its supported balance-workflow intervention acknowledges the existing supervisor notice and verifies both dismissal and member identity. Unresolved checks remain paused; cancellation or the total deadline stops the run.

The interactive discovery CLI exposes the existing bounded operator panel. Non-interactive mode returns HUMAN_REQUIRED and closes cleanly for CI. This is mediated live control, not arbitrary native-browser gesture recording. Other intervention types need explicit reviewed plans; the model cannot supply them.

# Safety

The browser adapter enforces an exact-origin allowlist with loopback defaults, blocks off-origin requests/redirects, and disables service workers, downloads, and WebSockets. Discovery accepts bounded typed actions only: no model-provided JavaScript, shell, HTTP requests, or raw selectors. Policy classifies operations independently of model assertions; risky unreviewed operations require a human, and irreversible replay actions are blocked or require configured review.

Malicious-looking page text remains observation data. Tests show that a proposed transfer cannot bypass the action schema and policy. This contains the tested behavior; it does not prove universal prompt-injection immunity or trustworthiness of an arbitrary application's labels.

Selective screenshot redaction masks known simulator sensitive fields before encoding and writing. Unknown coverage or unstable captures fall back to FULL_MASK with a manifest; DISABLED is also available. Evidence omits runtime PII, credentials, raw goals, and provider reasoning. Canary/secret-shape scans and pixel tests check that boundary. Tenant bindings cannot weaken policy, and replay never gains a model dependency through discovery or handoff.

# Cuts

The target is a local simulator, not a real bank system. Production authentication/IAM, signed artifacts, durable resume, and distributed workers are absent. Control/resume state remains in memory. Human controls are bounded and mediated: no arbitrary native browser takeover is implemented. A desktop adapter is an abstraction only.

Human-assisted successful discoveries retain evidence and require explicit review before compilation. Automatic compilation rejects them; the review/approval workflow is intentionally not implemented. The compiler supports a narrow verified balance workflow.

There is no automatic self-healing or LLM repair during replay. Redaction covers a reviewed simulator contract, not arbitrary PII discovery. Tested action constraints do not establish universal prompt-injection immunity. Health results are controlled evaluation evidence, not production reliability estimates.

Reproduction commands and the retained proofs are linked from [README](README.md) and the [evidence index](evidence/README.md).
