# Automated evaluation and failure analysis

## Run the suite

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_evaluation.py
```

Use `--scenario happy_path` to select one scenario or `--repeats 2` to repeat the selected suite. Repetitions are bounded to 1–20. No key or LLM is needed. A nonzero exit means a scenario produced an unexpected status/classification/output, not merely that an intentionally failing workflow stopped.

The runner loads the same generated `get_member_balance@1.0.0` and existing tenant bindings. Each trial starts a fresh application session and runs through the normal tenant preflight, binding resolver, ReplayEngine, locator/policy services, and Surface. The evaluator accepts a Surface factory; it imports no Playwright provider itself.

## Scenarios

| Scenario | Controlled condition | Expected result |
|---|---|---|
| happy_path | Bank A baseline | SUCCESS |
| primary_failure_fallback_success | Bank A label drift; stable CSS remains | SUCCESS with PRIMARY_LOCATOR_FAILED finding |
| all_locators_failed | Input remains a textbox but all configured aliases/IDs differ | FALLBACK_EXHAUSTED |
| required_element_missing | Lookup input absent | REQUIRED_ELEMENT_MISSING |
| stale_member | Different member displayed after search | PAGE_STATE_INVALID |
| partial_page_load | Search leaves the application in a loading state | PAGE_STATE_INVALID / PARTIAL_PAGE_LOAD |
| tenant_baseline | Bank B binding | SUCCESS |
| tenant_label_drift | Bank B label changes, fallback remains valid | SUCCESS |
| tenant_structural_drift | Additional Bank B wrappers | SUCCESS |
| ambiguous_control | Duplicate Find Customer controls | HUMAN_REQUIRED / AMBIGUOUS_TARGET |
| value_not_retained | Input event clears the entered value | POSTCONDITION_FAILED |
| unexpected_workspace | Maintenance workspace replaces lookup | PAGE_STATE_INVALID |
| member_not_found | Valid negative business result | BUSINESS_OUTCOME / MEMBER_NOT_FOUND |

Faults alter the simulator UI, not the capability or binding. The stress mix intentionally contains many failures; its aggregate success rate is not a production reliability estimate.

## Failure analysis

Classification consumes the actual RunResult, locator events, the effective capability's checkpoint definitions, and freshly observed redacted page facts. It does not select a reason merely from the injected scenario name.

Machine-readable reasons include PRIMARY_LOCATOR_FAILED, FALLBACK_EXHAUSTED, REQUIRED_ELEMENT_MISSING, PRECONDITION_FAILED, POSTCONDITION_FAILED, PAGE_STATE_INVALID, PARTIAL_PAGE_LOAD, AMBIGUOUS_TARGET, POLICY_REVIEW_REQUIRED, and ENGINE_FAILURE for otherwise unclassified engine failures.

A successful fallback has a diagnostic finding, not a failed-run classification. Business outcomes also have no infrastructure-failure classification. Every unsuccessful run retains the original engine code, step/condition IDs, additional findings, and links to source evidence.

The evaluator distinguishes absent lookup controls from unrecognized locators by observing whether the expected input role remains present. It checks the known unexpected-workspace region through Surface, and compares displayed identity to the requested identity in memory. Only booleans are persisted. These are bounded simulator diagnostics, not universal root-cause inference for arbitrary applications.

One existing evidence bug was corrected: ReplayEngine now retains the currently active checkpoint during a timeout, so a precondition timeout cannot be mislabeled as a postcondition timeout. Execution order, policy, and retry bounds remain unchanged.

## Metrics and methodology

The report includes:

- total runs, raw SUCCESS count, business outcomes, and reliable completion rate;
- primary locator success and fallback usage per action-target resolution;
- fallback recovery among runs that actually attempted a non-business fallback;
- terminal unsuccessful runs after bounded recovery (HARD_FAILURE or RECOVERABLE_ERROR);
- human-required/handoff rate;
- deduplicated drift-event count;
- scenario expectation pass rate;
- machine-readable failure counts and the most common failure.

Locator denominators exclude checkpoint polling and expected-absent business probes, reusing the health extractor's deterministic metrics. Fallback recovery has a different, explicit denominator: successful/business-outcome runs with fallback divided by all runs that attempted fallback.

“Unrecoverable” means the bounded execution ended unsuccessfully; it does not claim that manual repair is impossible. HUMAN_REQUIRED is reported separately. Statuses and classifications are both preserved.

Every successful balance trial also checks the exact expected fictional balance in memory. The expected member/balance are excluded from persisted Scenario serialization. An output mismatch fails the scenario expectation even if the engine returned SUCCESS; the report preserves both observed engine status and oracle result.

Deterministic evaluation matters because a plausible-looking click sequence is insufficient evidence of correctness. Controlled faults make identity checks, fallback behavior, ambiguity stops, and verification failures repeatable. This allows regressions to be compared quantitatively without relying on a model's explanation of what happened.

## Output and traceability

```text
evidence/evals/<evaluation-id>/
  summary.json        aggregate metrics and typed per-run results
  results.jsonl       completed trial records, written as trials finish
  methodology.json   scenario definitions, repetitions, and denominators
  README.md           generated reviewer index
  runs/<run-id>/      original replay metadata, events, results, telemetry, masked captures
```

Each run record includes extracted RunMetrics, a source-evidence digest, redacted page facts, failure analysis, fallback flags, and expectation/oracle results. The canonical artifact is checked unchanged. Model imports are blocked in the fresh CLI process; model credentials are removed and no model module may load.

Raw runtime values, page text, credentials, and selectors are not copied into failure-analysis records. Screenshot masking follows the existing policy.

## Interpretation and limits

The [completed browser evaluation](../evidence/evals/3dbc86c3ef07491c85270bbf96790974/summary.json) exercised all 13 scenarios with 100% expectation agreement and zero model calls. Reliable completion was 46.2% (5 successes plus 1 business outcome), primary locator success 91.3% (21/23 action resolutions), fallback usage 8.7% (2/23), fallback recovery 40% (2/5 fallback-attempting runs), terminal failures 46.2% (6/13), and human intervention 7.7% (1/13). It recorded seven drift events; PAGE_STATE_INVALID was the most frequent failure. Earlier evaluation directories retain the actual unsuccessful development checks rather than being overwritten.

The default suite is deliberately adversarial. A safe refusal in a negative scenario counts as an evaluation expectation passing, while remaining an unsuccessful workflow in the execution metrics. Always inspect both rates.

Scenario fixtures and balance oracles are specific to the member-balance workflow. The runner is separate from the engine, but additional business workflows need their own input/output oracles and page-state facts. The named loading/maintenance markers are simulator contracts.

The framework does not repair capabilities, mutate bindings, promote human actions, or introduce a second automation engine. Browser timing remains measured rather than assumed identical across runs. A browser/setup exception can leave a partial evaluation directory with completed results and no final summary; treat that as incomplete evidence.

See [capability health](health.md) for longer-window fragility assessment. Do not mix injected-failure evaluation traffic into ordinary health populations without identifying that choice.
