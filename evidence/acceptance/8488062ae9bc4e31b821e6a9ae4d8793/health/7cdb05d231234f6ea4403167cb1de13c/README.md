# Capability health evaluation

Actual Chromium/simulator replay. All baseline and label-drift runs succeeded.
Bank B then became DEGRADED from measured locator fallback usage; Bank A stayed HEALTHY.

## Derived snapshots

- [bank_a_baseline](derived/bank_a_baseline/get_member_balance/1.0.0/ebc885d2fa374146a5dc4ce280b6d402/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [both_baseline](derived/both_baseline/get_member_balance/1.0.0/a5ef495e77ad4909b66db09f25866ca5/summary.json): summary, run metrics, thresholds, and source evidence digests.
- [successful_drift](derived/successful_drift/get_member_balance/1.0.0/6677c3630ef84d5c9ed29e9d4f88dd3e/summary.json): summary, run metrics, thresholds, and source evidence digests.

Source run IDs and scenario configuration: [evaluation.json](evaluation.json).
Original replay evidence lives under runs/<run_id>/. Derived runs.jsonl links each source directory.
No capability or binding was rewritten. No model calls were used.
