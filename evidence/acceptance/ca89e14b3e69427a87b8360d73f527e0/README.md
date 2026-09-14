# Final submission completion evidence


- [Discovery handoff with scripted decisions](discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/report.json)
- [Discovery handoff with real Gemini decisions](live-handoff/011a662b0bed41a498c245a379aed91e/report.json)
- [Real unassisted discovery, compilation, different-input zero-model replay](live/report.json)

Both takeover runs use a clearly labeled scripted operator with the existing bounded action. The live case invokes Gemini four times, acknowledges the notice once, and succeeds in the same session. It does not automatically compile the human-assisted trajectory.

Original source records are copied byte-for-byte. Paths retain their original ignored local root; [archive-manifest.json](archive-manifest.json) maps retained copies and hashes. Repeated health/evaluation traces stay local and have prior representative evidence in the earlier acceptance archive.

## Representative redacted screenshots

- [discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/handoff_1.png](discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/handoff_1.png)
- [discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/handback_1_1.png](discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/handback_1_1.png)
- [discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/5.png](discovery-handoff/407c1afb6b6740e3a300d1aac3e67073/runs/823887aebba94a52931c514ea83e562b/screenshots/5.png)
- [live/business/1997d773741e47c387de77f39e14ad94/screenshots/final.png](live/business/1997d773741e47c387de77f39e14ad94/screenshots/final.png)
- [live/discovery/0d722350416e48fd8c73cf92ff66bf55/screenshots/4.png](live/discovery/0d722350416e48fd8c73cf92ff66bf55/screenshots/4.png)
- [live/validation/7c1d44aff2fe4e9cba565c8161bea162/screenshots/final.png](live/validation/7c1d44aff2fe4e9cba565c8161bea162/screenshots/final.png)
- [live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handoff_1.png](live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handoff_1.png)
- [live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handback_1_1.png](live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/handback_1_1.png)
- [live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/5.png](live-handoff/011a662b0bed41a498c245a379aed91e/runs/0d072fa6487540ed8e0841b5a1dff5a2/screenshots/5.png)

## Cleanup selection

The original archive manifest remains unchanged. These aggregate reports are intentionally excluded because their command strings contain machine-specific absolute paths: `checks.json`, `report.json`. Component run records remain unchanged and their hashes can be checked against the manifest. Omitted entries are not missing successful-run evidence. Use the [submission evidence map](../../README.md) and [current verification](../../../docs/cleanup.md).
