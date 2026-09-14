# Successful live Gemini retry

This is the real run after updating the local credential, not a mock or a rerun of the full test suite. The [original report](report.json) records all four claims as PASS:

- [Discovery](discovery/647f83d2efdb4203836fe8fb46e96c4f/result.json): Gemini, six calls including retries; verified trajectory files are adjacent.
- [Compiled DRAFT](artifacts/get_member_balance/1.0.0/draft.json) and [VALIDATED artifact](artifacts/get_member_balance/1.0.0/validated.json): generated from this run, separate from the canonical repository capability.
- [Different-input replay](validation/a7e113edc24045959dd31b58116d18a2/result.json): expected identity/balance verified in a fresh worker, zero model calls, no model credentials or loaded model modules (see report).
- [Business outcome](business/207d75ba21b043028e953ead6f8ac000/result.json): MEMBER_NOT_FOUND, zero model calls.

[Representative redacted replay screenshot](validation/a7e113edc24045959dd31b58116d18a2/screenshots/final.png) preserves headings and layout; its [manifest](validation/a7e113edc24045959dd31b58116d18a2/screenshots/final.png.json) documents selective masking.

All source text records and the selected screenshot were copied byte-for-byte. The [archive manifest](archive-manifest.json) maps original local paths to retained copies and hashes. Other images are intentionally omitted; their capture manifests and original references remain unchanged. The earlier [failed attempt](../cleanup-live-failure/report.json) is retained separately. This retry does not replace the separate historical discovery-handoff proof.
