# 2. Compile verified behavior

**What this proves:** The Primary reviewer run's verified trajectory becomes a typed, versioned capability through CapabilityCompiler.

**What happened:** The compiler selected verified source sequences 2, 4 and 5, parameterized the member identifier, and emitted `get_member_balance@1.0.0` as DRAFT. Different-input validation then produced a separate VALIDATED snapshot. This run's artifact lives inside its evidence bundle; it does not replace the repository's older canonical capability.

**Best evidence files:**

- [Source fill](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/trajectory-002.json), [search](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/trajectory-004.json) and [extraction](../acceptance/key-retry-20260914-1/discovery/647f83d2efdb4203836fe8fb46e96c4f/trajectory-005.json): executed and verified source actions.
- [Compiled DRAFT](../acceptance/key-retry-20260914-1/artifacts/get_member_balance/1.0.0/draft.json): inspect `inputs`/`outputs` (string member ID, decimal balance), ordered `steps`, semantic target strategy lists, pre/postconditions, final `success`, and `business_outcomes`.
- [VALIDATED artifact](../acceptance/key-retry-20260914-1/artifacts/get_member_balance/1.0.0/validated.json) and [validation record](../acceptance/key-retry-20260914-1/artifacts/get_member_balance/1.0.0/validations/a7e113edc24045959dd31b58116d18a2.json): lifecycle, capability version and discovery/compiler/validation provenance.
- [Pipeline assertions](../acceptance/key-retry-20260914-1/report.json): parameterization, observed strategies and immutability passed.

**Result:** Compilation and validation passed. DRAFT was not overwritten. VALIDATED records successful validation; it is not production approval or a cryptographic authorization claim.

**Why it matters:** Reviewed contracts and checkpoints make successful behavior reusable without asking a model to choose the steps again. Unsupported or human-assisted trajectories do not silently become unattended capabilities.

[Next: zero-LLM replay](03_zero_llm_replay.md) · [All five proofs](../README.md)
