# Capability health evaluation

Actual Chromium/simulator replay. All baseline and label-drift runs succeeded.
Bank B then became DEGRADED from measured locator fallback usage; Bank A stayed HEALTHY.

## Derived snapshots

- [bank_a_baseline](derived/bank_a_baseline/get_member_balance/1.0.0/4b72b30a65154bacb0cfb0e02b305047/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [both_baseline](derived/both_baseline/get_member_balance/1.0.0/e98261ca088d4eb586eda3fd643ee046/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [successful_drift](derived/successful_drift/get_member_balance/1.0.0/db35521fb1c74620bbd63851b1fcfed6/summary.json): summary, run metrics, thresholds, and source evidence digests.

Source run IDs and scenario configuration: [evaluation.json](evaluation.json).
Original replay evidence lives under runs/<run_id>/. Derived runs.jsonl links each source directory.
No capability or binding was rewritten. No model calls were used.
