# Milestone 3: real model-driven discovery

Discovery asks a model to choose individual UI actions against the live simulator. It does not load a capability artifact, call ReplayEngine, or import the simulator's record data. The optional account-preparation discovery workflow is intentionally deferred; the supported success contract is verified member savings-balance retrieval.

## Run a real discovery

Install the existing dependencies and Chromium as described in the README. Set credentials in the environment or in the ignored root `.env`:

```dotenv
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=gemini-3.5-flash
```

`GEMINI_API_KEY` is required. `GEMINI_MODEL` is optional and defaults to `gemini-3.5-flash`. An explicit CLI `--model` takes precedence over the environment, which takes precedence over `.env`. The small `.env` reader recognizes only these two names and does not execute shell expressions. Existing environment variables are not overwritten. Never commit credentials.

From the repository root:

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
.venv/bin/python examples/run_discovery.py --model gemini-3.5-flash \
  --goal "Find member 48321 and retrieve their savings balance."
```

This command starts an ephemeral **real local HTTP simulator**, launches **real Chromium**, calls **real Gemini**, then closes the browser/server after the result. It sends the natural-language goal and compact fictional UI observations to Google; it does not send screenshots, full HTML, credentials, environment variables, or capability artifacts. It prints safe status and accounting information, not the member ID or balance.

To use a manually started simulator, or watch the browser:

```sh
.venv/bin/python -m bank_simulator.server
# In another terminal:
.venv/bin/python examples/run_discovery.py --url http://127.0.0.1:8765/ --headed

# A business-outcome goal:
.venv/bin/python examples/run_discovery.py \
  --goal "Find member 99999 and retrieve their savings balance."
```

Only loopback HTTP URLs are accepted by the demonstration CLI. It accepts a goal containing `member` followed by a five-digit identifier and the words `savings` and `balance`. That identifier becomes the trusted input binding and verification contract. The sequence of UI actions is selected by the model, not parsed from a known workflow.

## Verified live run

A genuine run using `gemini-3.5-flash` returned `SUCCESS / VERIFIED_BALANCE`:

- 4 model calls: FILL, CLICK, EXTRACT, COMPLETE.
- 2,541 input tokens, 318 output tokens, and 766 thinking tokens reported by the provider (count only; no thinking content persisted).
- 33,131.828 ms measured discovery latency.
- Local evidence: `evidence/discovery/01d663a4539c44ab9aa368010f1bdbe3/`.

These are measurements from an actual execution, not fixtures. The directory is ignored and will not exist in a fresh clone; rerun the command to produce a new bundle. Earlier attempts also remain locally: Gemini 2.5 returned HTTP 404, and Gemini 3.8 returned HTTP 503 after its first successful decision. Those runs were recorded as failures, not replaced with mock success. Provider availability and model output can vary; the default is the model that completed the verified run.

## Dependency direction and interfaces

```text
CLI -> DiscoveryOrchestrator -> ModelClient <- GeminiModelClient / MockModelClient
                    |
                    +-> Surface <- PlaywrightSurface
                    +-> LocatorResolver
                    +-> PolicyEngine
                    +-> shared EvidenceWriter + discovery privacy projection
                    +-> typed trajectory and result

ReplayEngine -> Surface + domain services (no discovery/model dependency)
```

`ModelClient.decide(goal, observation, history, available_actions)` returns a typed `ModelReply` containing a `ModelDecision` and token usage. All Gemini endpoint, authentication, environment loading, prompt configuration, response parsing, and transport code is isolated in `discovery/gemini_client.py`. The implementation uses the standard-library HTTP client with Gemini's [structured-output REST API](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en); no vendor computer-use runtime or model SDK is required.

`Observation` now optionally contains page path, title, bounded visible text, observed elements, dialogs, and frame metadata. Existing targeted observations remain compatible. The browser adapter collects at most 80 candidate elements and sends at most 4,000 characters of visible text. Element IDs are local to the observation; names, roles, labels, kinds, enabled state, and input values support model decisions. Password inputs and hidden inputs are excluded. Frame metadata is descriptive; interactive frame traversal is still unsupported. No raw browser objects cross Surface.

`ModelDecision` supports CLICK, FILL, EXTRACT, WAIT, SELECT, COMPLETE, FAIL, and REQUEST_HUMAN. UI actions reference a current observation ID, never a model-written selector. FILL/SELECT uses the declared `member_id` binding; EXTRACT names the declared `savings_balance` output. CLICK/WAIT requires a short expected visible-text checkpoint. Unsupported values, fields, targets, or malformed output are rejected. SELECT is offered only by surfaces that declare support; the browser adapter implements it, although the first workflow does not need it.

The orchestrator revalidates adapter results, detects stale observations, resolves semantic targets through the existing LocatorResolver, applies policy, executes through Surface, and verifies the new observation. FILL checks the resulting field value; CLICK checks an observed state change and expected text; WAIT checks expected text; EXTRACT uses exact finite decimal parsing plus member-identity checks. COMPLETE requires a prior extraction, the requested member still displayed, and a current balance matching the extracted value. A model cannot invent an output or declare success without UI evidence.

## Safety and bounds

Risk comes from trusted code in `discovery/safety.py`, never the model. The local profile permits member-identifier entry, the Search button, and reading balances. Other writes/clicks are sensitive; confirmation/deletion/transfer-like controls are irreversible. PolicyEngine's shared operation gate requires human review for unreviewed sensitive/irreversible actions even if a caller supplies an ALLOW rule. Default read/reversible-write decisions remain configurable. Target-free WAIT is also policy-gated.

Unexpected dialogs stop discovery before the next decision. Ambiguous resolution stops without selecting the first match. No scripts, shell actions, arbitrary input values, arbitrary navigation, or direct browser calls are available to the model. Visible page content is marked as untrusted data in the prompt; policy remains the enforcement boundary.

Default limits:

- 12 decision attempts, with a hard configurable maximum of 30.
- 120 seconds overall, including observations, provider waits, screenshots, and retries.
- 4 seconds per UI action/checkpoint.
- Stop on the third repeated state/action/target combination.
- Stop after three consecutive action failures or transient provider failures.

Transient HTTP 429/500/503 and connection errors can retry the **model decision**, with a two-second delay. Each attempted call counts toward the decision and elapsed budgets. The code does not automatically replay a UI action. Invalid structured output fails immediately. Model calls use a 30-second transport timeout; a cancelled background HTTP request may remain in flight until that timeout and may still be billed.

`DiscoveryResult` distinguishes SUCCESS, BUSINESS_OUTCOME, HUMAN_REQUIRED, HARD_FAILURE, STUCK, and MAX_STEPS_EXCEEDED. Timeout exhaustion is a structured HARD_FAILURE with `ELAPSED_TIME_LIMIT`. Simulator business messages are recognized from observed alert text, not from model claims.

## Trajectory and evidence

The shared EvidenceWriter creates metadata, JSONL events, result JSON, and masked screenshots. Discovery adds privacy-projected observation and trajectory JSON files in that same run directory, with `execution_mode=llm_discovery` and `actor=MODEL`.

Trajectory entries contain the decision, semantic target, actual resolution strategy/quality, before/after observations, timestamp, duration, previous-failure count, verification evidence, and these distinct flags:

- `attempted`: a UI operation was dispatched or waiting began.
- `executed`: the Surface call returned, even if later verification failed.
- `verified`: the observed postcondition passed.
- `compilation_eligible`: the action was executed and verified; terminal decisions and rejected/uncertain actions are ineligible.

Only successful whole-run trajectories are accepted by the [Milestone 4 compiler](compiler.md). An individual eligible step is not blanket approval for compilation.

Full typed observations, decisions, semantic targets, trajectory, goal, and outputs remain in the returned in-memory result. Disk records omit runtime values and raw visible text, redact unknown labels, omit free-form model reasoning, and record a short generic operational reason. Screenshots remain fully masked. Provider responses and thought parts are never persisted. The logged goal substitutes the member identifier; output records show their type and a redaction marker. Consequently, disk evidence is auditable but is not a lossless compiler input; Milestone 4 consumes the in-memory trajectory and excluded-from-serialization invocation bindings.

Final results include provider, configured model name, total model-call attempts, token usage from successful structured replies, and total latency. HTTP errors do not expose token usage. Deterministic `RunResult` now explicitly has `model_calls=0`; ReplayEngine still imports no model component.

Existing tracked replay evidence is untouched. Only new `evidence/discovery/` is ignored, alongside `.env`.

## Tests and files

```sh
.venv/bin/pyright
.venv/bin/python -m pytest -q
RUN_BROWSER_TESTS=1 .venv/bin/python -m pytest -q
```

Regular tests use MockModelClient and do not need a key. Browser tests use MockModelClient with the real simulator, Chromium, Surface, resolver, policy, and orchestrator. The real CLI command above is the opt-in provider integration path.

Added `src/discovery/{models,model_client,gemini_client,mock_client,safety,evidence,orchestrator}.py`, `examples/run_discovery.py`, and discovery unit/browser tests. Extended portable observations, Surface selection, the browser observation adapter, shared policy/evidence entry points, and replay's zero-call result metadata. Milestone 3 itself generated no deterministic capability; Milestone 4 adds that bridge separately.

Remaining fragile areas: accessible-name normalization is a bounded approximation rather than a full accessibility-tree implementation; frame interactions are unsupported; the read-only safety/success contract is intentionally simulator-specific; semantic text checkpoints are weaker than transaction-bound assertions; projected evidence cannot reconstruct sensitive values; provider output and availability remain nondeterministic. Observation races are checked conservatively but browser operations are not atomic transactions.

The [Milestone 5 handoff layer](handoff.md) adds operator takeover separately. [Milestone 6](tenants.md) adds tenant bindings separately. Health aggregation, drift dashboards, automatic healing, and persistent/distributed infrastructure remain unimplemented.

[Capability health](health.md) now derives explainable assessments from replay evidence. [Automated evaluation](evaluation.md) adds controlled failure scenarios separately; automatic repair/healing remains unimplemented.
