# Evidence run architecture

Every public execution demo and acceptance command creates a new bundle automatically under `evidence/runs/<run-id>/`. Each bundle starts with README, summary and manifest plus five categories: discovery, replay, handoff, multitenant and evaluation. The existing UI writers still write their original redacted records into category-local raw directories; the deterministic exporter adds readable entry files and references. No UI decisions, policies, retries, health formulas or screenshot masking are changed.

## Commands

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
# Complete local acceptance; live-provider stages explicitly skipped:
.venv/bin/python examples/run_acceptance.py
# Complete acceptance including real Gemini; eligible for current only if all required checks pass:
.venv/bin/python examples/run_acceptance.py --live-discovery
# Standalone evaluation uses the same history structure, but cannot replace current:
.venv/bin/python examples/run_evaluation.py
```

Standalone discovery, compilation, replay, simulator, handoff, tenant and health demo commands are wrapped by the same run writer. `--evidence-root DIRECTORY` (or the simulator's `--evidence`) selects an alternate bundle store inside the repository; it is not an unstructured raw destination. Internal subprocesses share their acceptance bundle instead of creating nested independent bundles. Low-level library/test writers and the private fresh-process replay worker still respect explicit caller-provided roots; they do not select the public reviewer view.

The historical `curate_acceptance.py` is a legacy archive tool, not part of new evidence generation. No manual export or cleanup step is needed for a new command.

## Structure and status

```text
evidence/
  README.md
  current -> runs/<designated-successful-run>
  runs/
    README.md
    <run-id>/
      README.md
      summary.json
      manifest.json
      discovery/
      replay/
      handoff/
      multitenant/
      evaluation/
```

Each category contains only material actually produced, plus a README explaining whether evidence is available. Raw execution IDs live inside categories, never as new top-level evidence folders. Friendly result files are exact copies or deterministic projections of recorded results, not new behavioral evidence.

`INCOMPLETE` denotes an active/interrupted unfinalized run. Finalization produces `FAIL` for failed checks/export errors, `PARTIAL` for standalone or skipped-stage acceptance, and `PASS` only for complete acceptance. Expected negative scenario outcomes can pass the evaluation. A standalone successful balance lookup remains a partial assignment proof.

Promotion requires all mandatory checks, genuine successful Gemini discovery, successful compilation, verified different-input replay with zero model calls and blocked imports/credentials, business-outcome verification, independent saved-evidence assertions, the full authoritative scenario set, and passing privacy checks. A failed or partial run never updates `current`. Older successes cannot displace a newer designated success.

`current` is an atomically replaced relative directory symlink. It points inside `runs`, duplicates no data, and works in a normal symlink-preserving clone. GitHub's web UI may display the link target rather than browse it; use the direct run link in the evidence index there. On systems configured to check out symlinks as text, open that relative target. The source run must be explicitly allowlisted when committing current; the ignore rules include current and only the selected retained run IDs. Other generated runs remain local.

## Provenance, privacy and authority

Manifest artifact paths resolve relative to their run directory. Each record includes its hash, category, execution/run identity, capability identity where available, and whether it was generated, materialized or copied from historical evidence. `recorded_path` and `original_source` map unchanged source references to bundled files; `acceptance.bundle.resolve_reference` resolves these paths after cloning. Original references are not rewritten merely because their files were materialized elsewhere.

Canonical capability snapshots are marked referenced-existing and retain original provenance; including a reference does not claim that a standalone command executed that capability. New live acceptance compilations write unique numeric versions to the authoritative `capabilities/generated` store and copy those bytes into their bundle for inspection. Historical validation artifacts that were generated in isolated evidence stores remain identified as historical snapshots; they are not falsely promoted into the canonical store.

No raw output values, credentials or provider exception text are added to summaries. Existing redaction remains responsible for screenshots; the bundle copies image bytes and per-image manifests unchanged. Privacy scans gate promotion. The full scenario population is exported from actual evaluation results, not a hard-coded count or a reduced sample.

## Historical migration

The complete historical acceptance run `ca89e14b3e69427a87b8360d73f527e0` was imported from its original full local bundle, independently rechecked and designated current. All copied stage records are byte-identical. Host-specific root command reports were projected into new portable summaries; the redundant old source tree was subsequently removed after all copied files were verified byte-for-byte. The imported summary keeps original execution timestamps and explicitly identifies the source. Later isolated successful retries are not combined with it to invent a newer full acceptance pass.

Only three useful historical bundles remain: the full current acceptance, the canonical capability provenance chain, and the distinct real-Gemini handoff. Superseded acceptance, retry and development directories were deleted, without creating an archive. The canonical validation path remains as a relative compatibility link because the authoritative validation artifact explicitly references its three files. Other original source paths resolve through the retained manifests, not obsolete source trees.

## Retention policy

Generation and retention are separate. Every command initially writes its local run bundle; failed runs are retained during execution for debugging. New run IDs are ignored by Git. Retaining a run for submission requires adding that exact ID to the allowlist in `.gitignore`. Before committing an updated current pointer, retain its target too. This does not change acceptance promotion or delete any local runs automatically.

The import command is explicit and refuses an existing run ID:

```sh
.venv/bin/python -m acceptance.migrate PATH_TO_COMPLETE_OLD_ACCEPTANCE_ROOT
```

Migration uses the same completion gate. It cannot manufacture missing stages or turn a partial source into a fully successful current run.
