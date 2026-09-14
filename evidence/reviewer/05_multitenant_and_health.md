# 5. Reuse across tenants and detect degradation

**What this proves:** A capability can become fragile before it stops working. The same canonical flow serves Bank A and Bank B; increased fallback use makes Bank B DEGRADED while Bank A remains HEALTHY.

**What happened:** Supporting / historical evidence applies locator-only bindings to the existing canonical `get_member_balance@1.0.0`, then injects label drift. Unique fallback still completes the task. A separate 15-run controlled health population measures healthy baselines followed by successful Bank B drift runs.

**Best evidence files:**

- [Canonical capability](../../capabilities/generated/get_member_balance/1.0.0/validated.json), [Bank A binding](../../tenant_bindings/bank_a/1.0.0.json), [Bank B binding](../../tenant_bindings/bank_b/1.0.0.json): shared workflow; only locator strategies vary.
- [Scenario report](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenant-demos/6085ec575672402c8e3fd16e7ed011c2/scenarios.json): same canonical digest across tenants, zero model calls, drift counts and search counters.
- [Bank A result](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenants/d33edea1d76a4896a9f28ef4622702c6/result.json), [Bank B result](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenants/4265ac95bbbe437183c80eebebf251cc/result.json) and [Bank B label-drift result](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/reuse/tenants/04c51895361044eba3ddcb90b69d59a5/result.json): successful execution in each case; the scenario report records three drift signals for the label variant.
- [Health summary](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/health/7cdb05d231234f6ea4403167cb1de13c/derived/successful_drift/get_member_balance/1.0.0/6677c3630ef84d5c9ed29e9d4f88dd3e/summary.json) and [source run metrics](../acceptance/8488062ae9bc4e31b821e6a9ae4d8793/health/7cdb05d231234f6ea4403167cb1de13c/derived/successful_drift/get_member_balance/1.0.0/6677c3630ef84d5c9ed29e9d4f88dd3e/runs.jsonl): increasing fallback telemetry despite successful runs.

**Result:** All 15 health-demo executions succeeded. Bank A remained HEALTHY; Bank B became DEGRADED with 16.7% action-target fallback usage and an increasing-fallback trend. Safe fallback succeeds; ambiguous fallback candidates still stop.

**Why it matters:** Monitoring detects weakening locator reliability before total failure. Health is an explainable threshold assessment from controlled samples, not a calibrated probability or production reliability guarantee. It never automatically rewrites the capability.

**Provenance note:** The canonical tenant artifact correctly references an older discovery and validation run. It is not the new Primary reviewer run's artifact, despite sharing the capability ID/version in a separate store. Its immutable provenance and bytes remain unchanged; the [original validation record](../../capabilities/generated/get_member_balance/1.0.0/validations/c0a8057c3d2b40bb95d380807c51c33a.json) preserves that history.

[Return to the five-proof index](../README.md)
