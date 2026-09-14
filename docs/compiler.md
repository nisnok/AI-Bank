# discovery → compilation → deterministic replay

## Run the complete loop

Install dependencies and Chromium using the root README. Put `GEMINI_API_KEY=<your-key>` in the ignored root `.env`; `GEMINI_MODEL` is optional. Never commit the key.

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/discover_and_compile.py \
  --goal "Find member 48321 and retrieve their savings balance." \
  --member-id 48321 --validate-member-id 83921 --version 1.0.1
```

Use a fresh version each time: the demonstrated 1.0.0 already exists. The command starts a live local HTTP simulator and Chromium, calls real Gemini, compiles the successful in-memory trajectory, and saves a DRAFT. A fresh worker validates with a different input through the normal ReplayEngine. Success creates a separate VALIDATED snapshot. A second fresh worker replays the generated validated artifact with missing member 99999. Both workers start new browser sessions.

The CLI intentionally displays the fictional validation balance; persisted run evidence omits raw invocation/output values. Provider failure or unsupported trajectory stops the command. There is no mock fallback or manual-artifact fallback.

## Compiler contract and verification

`CapabilityCompiler.compile(discovery_result, capability_spec) -> CapabilityArtifact` is synchronous and deterministic. It has no provider calls, browser access, or artifact-file reads. The spec declares types, application identity, member-identity semantics, and the known MEMBER_NOT_FOUND application outcome; it contains no workflow steps. Manual examples are not compiler inputs.

Human-assisted discovery is rejected with HUMAN_ASSISTED_TRAJECTORY_REQUIRES_REVIEW; an explicit review/approval workflow is not implemented. Compilation requires successful unassisted discovery, ordered trajectory entries, typed input/output provenance, and verified COMPLETE. Only attempted, executed, verified, compilation-eligible UI actions become steps. Resolution must prove a unique observed target and a valid ordered attempt ladder. Proposed but unexecuted actions are omitted. Unsupported verified workflow shapes fail closed.

The current supported shape is FILL → CLICK → EXTRACT, with optional identity-verifiable waits. Mapping:

| Discovery evidence | Generated replay behavior |
|---|---|
| FILL with declared input binding and verified field value | Fill `{{ inputs.member_id }}`; visible precondition and value-equality postcondition |
| Verified Search click and subsequent observed member identity | Click learned target, then poll until requested identity is displayed |
| Observed savings target and matching typed extracted output | Decimal extraction with member-identity checks before and after |
| Verified COMPLETE with matching member | Final identity checkpoint; success also requires typed output extraction |

Search can show an intermediate processing state. Its completion checkpoint can come from the following read/wait observation; the compiler does not invent a locator from the model's expectation text. Ambiguous targets and stale identities retain the normal replay failure behavior.

Parameterization uses `DiscoveryResult.invocation_inputs` and the verified decision's `input_binding`. Invocation inputs are excluded from serialization. Only known input fields and identity expectations become template bindings; no unrestricted text replacement occurs. The discovery balance establishes output verification, never a constant replay output.

Targets retain observed semantic strategies, sorted accessibility → label → text → relative → CSS. Duplicate strategies and strategies containing known runtime input/output values are removed. The successful strategy must survive. No coordinates or invented fallback locators are generated. A final scan rejects discovery input/output literals in reusable fields.

The artifact declares required string `member_id`, decimal `savings_balance`, provenance, version, compatibility, bounded steps, checks, and MEMBER_NOT_FOUND. The business outcome comes explicitly from the simulator application contract, not from an unobserved model claim.

## Lifecycle and files

New artifacts are DRAFT. Ordinary policy refuses DRAFT replay. `CapabilityValidator` first verifies that validation inputs differ from the trusted discovery invocation. Its temporary policy grants only reads/reversible writes for the exact bound artifact and steps; the normal ReplayEngine performs all UI operations, resolution, conditions, typed extraction, and evidence.

Successful replay creates VALIDATED plus the validation run ID. Failed replay keeps DRAFT and records the failure. The model cannot approve itself; `approved_for_replay` remains false. Ordinary policy recognizes validated generated low-risk artifacts while retaining configured risk gates.

`ArtifactStore` uses exclusive creation:

```text
capabilities/generated/get_member_balance/<version>/
  draft.json
  validated.json                 only after successful different-input replay
  validations/<run_id>.json
```

Draft bytes remain unchanged. Validation can add lifecycle/provenance but cannot alter workflow meaning. Later changes require a new version. Existing hand-authored artifacts stay in their original paths, described in [capabilities/README.md](../capabilities/README.md).

## Actual execution evidence

The completed real run on 2026-09-12 used Gemini `gemini-3.5-flash`:

| Phase | Actual result |
|---|---|
| Discovery, member 48321 | SUCCESS, 4 model calls |
| Compilation | get_member_balance@1.0.0, DRAFT |
| Validation, different member 83921 | SUCCESS, Decimal("807.20"), 0 model calls |
| Negative replay, member 99999 | BUSINESS_OUTCOME / MEMBER_NOT_FOUND, 0 model calls |
| Lifecycle | DRAFT → VALIDATED |

Discovery reported 2,557 input tokens, 321 output tokens, 587 thinking tokens (counts only), and 7,601.486 ms latency. Two earlier real discoveries succeeded but compilation rejected their intermediate Search state; their evidence was retained locally. The demonstrated artifact came from the subsequent new successful run after the compiler fix.

Evidence and artifact paths:

- Discovery source run ID: `6234bdefa80947b8856fbc677939560c` (original local-only run; the separate retained real-provider proof is linked in the [evidence index](../evidence/README.md)).
- Compilation and isolation report: `evidence/compilation/e1b022aa799f40b182e033a6753a7e0c/`
- DRAFT: `capabilities/generated/get_member_balance/1.0.0/draft.json`
- VALIDATED: `capabilities/generated/get_member_balance/1.0.0/validated.json`
- Validation replay: `evidence/validation/c0a8057c3d2b40bb95d380807c51c33a/`
- Negative replay: `evidence/generated-replay/770279a2f2fa4acdb4b33e8f7bc6751f/`

Discovery remains gitignored and exists locally; rerunning produces a new bundle. Compilation/replay evidence and generated artifacts can be retained with the repository. Historical opaque screenshots are omitted from the submission; unchanged text records preserve their original capture references. Representative selective and fail-closed captures are linked in [acceptance](acceptance.md). Persisted trajectories are privacy projections, not lossless compiler inputs; compilation uses the actual in-memory result.

## Credible zero-model separation

```text
Goal → DiscoveryOrchestrator → ModelClient + Surface → verified in-memory trajectory
Trajectory → CapabilityCompiler → portable CapabilityArtifact
Artifact → ReplayEngine → resolver + policy + conditions + Surface
```

The fresh replay worker installs an import guard rejecting discovery and provider modules. The parent removes Gemini and common provider credential variables from the worker environment. Worker reports verify no model modules loaded and no Gemini key present. The validation isolation report records these checks beside actual replay run references.

The normal ReplayEngine has no dependency on Gemini, ModelClient, or DiscoveryOrchestrator. Compiler validation/storage also import no discovery modules. Artifact models have no Playwright dependency. Static dependency tests and a real-browser fresh-worker test enforce these boundaries. The zero-call result field is therefore backed by structural and runtime checks, rather than only console text.

## Tests and limits

```sh
.venv/bin/pyright
RUN_BROWSER_TESTS=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python -m pytest -q
```

Tests cover deterministic compilation, invalid/incomplete trajectories, unexecuted proposals, typed parameterization and no literal leakage, learned locator order, checkpoints, asynchronous Search, provenance, DRAFT gating, different-input validation, unchanged draft storage, failure retention, real-browser replay, stale identity, MEMBER_NOT_FOUND, and model isolation.

Current limits:

- Compilation deliberately supports this narrow member-balance contract, not arbitrary SELECT/navigation/retry workflows.
- Validation trusts source invocation data supplied by the in-process caller. File lifecycle/provenance is a local trust convention, not signed approval or tamper-proof proof.
- File creation prevents overwrites through this API; multi-file persistence is not transactional and has no crash recovery.
- Accessibility naming is a bounded approximation. Normalized observations now use one DOM snapshot, but separate browser operations are not atomic transactions.
- The runtime-value scan protects known bindings/outputs; it is not a general sensitive-data classifier for unrelated application text. The supported simulator contract is intentionally narrow.
- Replay import guards and static boundaries are dependency checks, not an operating-system network sandbox.
- Masked screenshots and redacted disk trajectories limit retrospective debugging. No raw reasoning or credentials are persisted.

[Human handoff](handoff.md) implements same-session operator handoff separately. [Multi-tenant reuse](tenants.md) provides locator-only tenant bindings. Health aggregation is implemented separately; automatic healing, governance services, and distributed persistence remain out of scope.

[Capability health](health.md) now derives explainable assessments from replay evidence. [Automated evaluation](evaluation.md) adds controlled failure scenarios separately; automatic repair/healing remains unimplemented.
