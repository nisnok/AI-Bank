# Capability health evaluation

Actual Chromium/simulator replay. All baseline and label-drift runs succeeded.
Bank B then became DEGRADED from measured locator fallback usage; Bank A stayed HEALTHY.

## Derived snapshots

- [bank_a_baseline](derived/bank_a_baseline/get_member_balance/1.0.0/018bb002e8f742d380e9c3c9d51a5d81/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [both_baseline](derived/both_baseline/get_member_balance/1.0.0/9ec94c1f598349d594b3cce78c5d64e2/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [successful_drift](derived/successful_drift/get_member_balance/1.0.0/9e5ab5848f964c85ae11f006cd0d2e01/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [faults](derived/faults/get_member_balance/1.0.0/c71e06fa708b436fbbc414c37a8024ae/summary.json): summary, run metrics, thresholds, and source evidence digests.

Source run IDs and scenario configuration: [evaluation.json](evaluation.json).
Original replay evidence lives under runs/<run_id>/. Derived runs.jsonl links each source directory.
No capability or binding was rewritten. No model calls were used.
