# Capability health and reliability monitoring

Health consumes structured evidence; it does not execute workflows, rewrite artifacts, or call a model.

## Commands and genuine demonstration

```sh
# Fifteen genuine browser runs: healthy baselines followed by successful label drift.
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_reliability_eval.py

# Optionally add six ambiguity/incompatible-version runs.
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_reliability_eval.py --include-failures

# Recompute from an evidence population you explicitly choose:
.venv/bin/python -m capability_health.cli --capability get_member_balance --version 1.0.0 \
  --evidence evidence/tenants
```

The harness prints its evaluation directory. To recompute its final population, pass that directory's `runs` subdirectory to `--evidence`. Optional `--thresholds path.json` loads a strict Thresholds model; `--store path` selects the derived-data root.

The actual 21-run demonstration is indexed at
[evidence/reliability/cd5175d3d05e40d0bd1646db8d1bdd4a/README.md](../evidence/reliability/cd5175d3d05e40d0bd1646db8d1bdd4a/README.md).

| Phase | Bank A | Bank B | Overall |
|---|---|---|---|
| 5 Bank A clean runs | HEALTHY | no samples yet | HEALTHY |
| Add 5 Bank B clean runs | HEALTHY | HEALTHY | HEALTHY |
| Add 5 Bank B label-drift runs, all SUCCESS | HEALTHY | DEGRADED | DEGRADED |
| Add 3 Bank B ambiguity + 3 incompatible-version runs | HEALTHY | UNHEALTHY | UNHEALTHY |

At the successful-drift phase, all 15 executions succeeded. Bank B's action-target fallback rate was 16.7%, compared with 0% for Bank A. Bank B's latest five runs used fallback on 33.3% of action-target resolutions, versus 0% in its preceding five runs. Reasons included FALLBACK_USAGE_HIGH, PRIMARY_LOCATOR_MATCH_RATE_LOW, LOCATOR_DRIFT_OBSERVED, and FALLBACK_USAGE_INCREASING.

This is measured degradation while execution still succeeds. It is not an invented confidence score. All runs verified the expected fictional balance and used zero model calls. The canonical artifact's bytes were checked unchanged.

## Evidence → metrics → assessment

`capability_health.extract.extract_run` parses metadata, typed event records, result JSON, and available typed locator telemetry. It verifies run identity, terminal status, timestamp ordering, locator-attempt sequences, and telemetry identity. Extraction is deterministic and records a digest of its source files.

`load_runs` selects one capability ID/version and reports malformed/incomplete or duplicate bundles explicitly. Non-replay discovery/compilation evidence is excluded rather than mixing incompatible execution modes into replay reliability. A missing tenant becomes an explicit `unattributed` group; it is never assigned to Bank A by guesswork.

`RunMetrics` includes status/times, step count, locator attempts/successes/depth, ambiguity, known recoverable failures/retries, recovered steps, handoffs/actions, drift signals, validation outcome when marked, tenant/binding identity, source directory/digest, and model-call count.

Only one minimal telemetry addition was needed: validation replay now emits a `run_purpose=VALIDATION` event. Historical validation bundles lacking that marker have unknown validation purpose; they are not inferred from a filename. Existing locator, retry, handoff, and terminal evidence remains the measurement source.

## Metric definitions

- **Reliable completion / success rate:** (SUCCESS + BUSINESS_OUTCOME) / completed runs. MEMBER_NOT_FOUND is valid execution, not infrastructure failure. Raw successful-run and business-outcome counts remain separate.
- **Primary locator match rate:** primary successes / action-target resolution attempts.
- **Fallback rate:** successful non-primary resolutions / action-target resolution attempts. A step attempted again during a bounded retry contributes another measured resolution attempt.
- **Locator denominator:** excludes pre/postcondition polling and expected-absent business probes. This prevents repeated “not found” checks from manufacturing poor locator reliability.
- **Ambiguity:** distinct step/condition resolution sites per run; ambiguity rate is the fraction of runs with any ambiguity.
- **Recovery rate:** fraction of runs with a recorded retry. Recovery attempts count retry decisions; successful recoveries count retried steps that ultimately succeeded or returned a business outcome.
- **Recoverable errors:** known retry-triggering failures plus a terminal RECOVERABLE_ERROR. Existing evidence does not expose every internally caught exception; this is an observed count, not an exhaustive exception trace.
- **Human intervention:** runs with HUMAN_REQUIRED, recorded handoff, or human actions. Expected policy escalation remains distinct from hard failure and is not automatically classified UNHEALTHY on its own.
- **Drift rate:** runs with a drift signal / runs. Drift counts deduplicate repeated samples at the same step/condition/reason.
- **Latency:** measured run_finished duration, including human waiting if present. Missing durations remain unavailable. p95 uses nearest rank; sample count is shown.

Rates use Decimal and four decimal places in JSON; the CLI displays percentages to one decimal place. These are ratios of explicit counts, not probabilistic confidence.

## Demo thresholds and bounded trends

Defaults are configurable engineering choices, not industry standards:

- Fewer than 5 runs: INSUFFICIENT_DATA.
- Fallback above 10%, primary match below 90%, recovery above 10%, or intervention above 10%: DEGRADED reasons.
- Observed drift, ambiguity, hard failure, or exhausted recovery also recommends review.
- At least 2 hard-failure runs and at least a 10% hard-failure rate: UNHEALTHY.
- At least 2 ambiguous runs and at least a 10% ambiguity rate: UNHEALTHY.
- Reliable completion below 80% with repeated hard-failure/ambiguity evidence: UNHEALTHY.
- Trends compare the latest 5 completed runs with the preceding 5, only when both windows are full. A rate change of at least 15 percentage points emits the relevant trend reason.
- Latency regression requires complete samples in both windows, at least 1.5× mean latency, and at least 100 ms increase.

Trend windows are per tenant; global mixing does not manufacture a trend from changing tenant proportions. Overall status cannot hide a degraded/unhealthy tenant behind a healthy global average. A tenant with insufficient evidence prevents an otherwise healthy global assessment from claiming complete coverage. Excluded malformed evidence is reported in the summary.

A configured “high fallback” threshold does not erase independent evidence of drift or ambiguity. Reasons are separately observable and inspectable.

## Derived storage and optional policy context

`HealthStore` writes exclusive snapshots under:

```text
health/<capability>/<version>/<snapshot-id>/
  summary.json
  runs.jsonl
  thresholds.json
```

The evaluation harness stores equivalent snapshots inside its evidence directory by phase. Each metric links the original run directory and source digest. These files are explicitly marked derived data; recompute them from evidence rather than editing assessments. No immutable capability or binding is changed.

Recommendations are separate from artifact lifecycle: REVIEW_RECOMMENDED or NEEDS_REVALIDATION. There is no automatic VALIDATED→INVALID transition or numerical kill switch.

An optional `ReliabilityPolicy` adapter accepts an explicit capability/tenant assessment. It first applies normal policy. It can turn an otherwise-allowed irreversible action into REQUIRE_HUMAN for a DEGRADED/UNHEALTHY tenant. Existing BLOCK/REQUIRE_HUMAN decisions remain intact; read/reversible actions keep normal decisions. The adapter is configurable and is not automatically injected into replay by aggregation.

## Limits

These are engineering assessments of a selected evidence population, not statistical guarantees. Deliberately injected stress failures should not be confused with production traffic. Bindings, evidence files, and supplied historical assessments remain trusted local inputs; hashes detect changes when compared, not malicious authorship.

There is no continuous monitoring service, authenticated health distribution, expiry policy, automatic repair, lifecycle mutation, dashboard, database, or distributed infrastructure. ReplayEngine imports no health subsystem or model client.
