# Acceptance verification

Use the [evidence map](../evidence/README.md) to inspect the strongest proof for each assignment claim. The retained bundles contain real executions against local Chromium and the fictional simulator. Real Gemini records are distinguished from scripted model decisions and scripted operator actions.

## Reproduce

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_acceptance.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright" .venv/bin/python examples/run_acceptance.py --live-discovery
```

The runner executes normal tests, opt-in browser tests, pyright, all 13 evaluation scenarios, tenant reuse, health, replay handoff, discovery handoff, recovery, independent saved-evidence assertions, and privacy scans. New runs are automatically organized under `evidence/runs/<run-id>/`. Fully successful acceptance can update `evidence/current/`; failed/partial runs cannot. See [the evidence architecture](evidence.md). Live discovery requires a local Gemini key; missing keys are explicitly skipped, provider failures are FAIL, and dependent claims are skipped. No mock result substitutes for real discovery.

Historical completion verification passed 215 normal tests and 37 separate browser tests, with zero type errors. [Real unassisted discovery](../evidence/current/discovery/raw/live/report.json) passed compilation and isolated different-input replay; [real Gemini handoff](../evidence/runs/011a662b0bed41a498c245a379aed91e/handoff/raw/discovery/011a662b0bed41a498c245a379aed91e/report.json) completed in four calls with one scripted operator action. These historical passes do not guarantee current provider availability. The retained checks are recorded in [current acceptance](../evidence/current/evaluation/acceptance.json).

## Handoff semantics

Interactive discovery and replay share HandoffManager and SessionController. HUMAN_REQUIRED pauses the same session; taking control grants HUMAN ownership and blocks automation UI actions. Supported human actions are audited. Handback requires a fresh observation and trusted identity/state checkpoints. Discovery discards cached output and requests a new decision; replay does not repeat a completed human confirmation.

Discovery currently supports supervisor-notice acknowledgement. Other interventions remain paused for inspection/cancellation until the total deadline. Non-interactive discovery returns HUMAN_REQUIRED and closes. Successful human-assisted discovery retains evidence but is not automatically compiled: explicit review/approval would be required, and that workflow is intentionally not implemented. Acceptance operators are scripted; a person can use the same panel through the interactive commands.

## Evidence selection and integrity

Two curated archives cover complementary claims: the initial hardening archive contains recovery, evaluation, tenant/health telemetry, replay handoff and a retained provider 503 failure; the completion archive adds real discovery-time takeover and a fresh unassisted pipeline. Canonical capability provenance remains at its original paths.

Successful raw JSON/JSONL and screenshots are unchanged. Each retained run manifest preserves hashes and original-source mappings. Superseded source trees and retry directories were deleted after comparing the retained copies byte-for-byte. Original recorded paths are historical identifiers resolved through the manifests; they do not require the obsolete local directories. See [retention policy](evidence.md#retention-policy).

## Screenshot privacy

Selective redaction is the default for the trusted simulator privacy profile. Inputs, table values, sensitive fields and embedded content are masked before encoding/writing; labels, headings, buttons and layout remain visible. Per-image manifests record coverage and policy, never masked values. Unknown/incomplete/unstable coverage causes FULL_MASK; DISABLED is also supported.

The first archive intentionally retains two opaque fallback images with `fallback_full_mask=true`. They demonstrate fail-closed privacy, not usable visual debugging. Other retained image examples are selectively redacted. Pixel tests check sensitive masks and visible headings; representative actual captures are visually inspected. Legacy all-black captures without a useful privacy manifest are excluded.

## Security and limits

Exact-origin controls block off-origin requests/redirects; service workers, downloads and WebSockets are disabled. Typed discovery actions exclude model-provided scripts, shell, raw selectors and arbitrary URLs. Policy remains authoritative. Tested injection containment is not universal prompt-injection immunity.

Text scans check credential shapes, current key values and fictional PII canaries without printing matches. They are bounded checks, not general DLP. Fixtures intentionally contain fictional banking data. Selective redaction needs a reviewed profile. Artifacts are trusted local configuration; operator authentication and in-memory resume are demonstration scope. Health/evaluation results describe controlled scenarios, not production reliability.

```sh
.venv/bin/python -m acceptance.privacy --repository --evidence evidence/current
```

## Latest live pipeline verification

The retained full acceptance proves the live pipeline. Superseded standalone retries were removed rather than retained as duplicate proof. Fresh provider errors do not replace the designated current success.