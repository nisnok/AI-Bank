# Curated acceptance evidence


Source JSON/JSONL is copied byte-for-byte. Original paths refer to the ignored local run root; the archive manifest maps them to these retained files. Image manifests for omitted images describe original captures; only the representative images below are included.

## Representative safe screenshots

- [live/discovery/378ac3811fb447f8b82b9bed3c362e2a/screenshots/3.png](live/discovery/378ac3811fb447f8b82b9bed3c362e2a/screenshots/3.png)
- [live-retry/discovery/eabe5b06931b4f8cba2266ef8ae1ccfb/screenshots/4.png](live-retry/discovery/eabe5b06931b4f8cba2266ef8ae1ccfb/screenshots/4.png)
- [live-retry/validation/33f1407521cc4aec9dc205106d43d013/screenshots/final.png](live-retry/validation/33f1407521cc4aec9dc205106d43d013/screenshots/final.png)
- [live-retry/business/de9ca6c7d970452da70317f8c5fdd68d/screenshots/final.png](live-retry/business/de9ca6c7d970452da70317f8c5fdd68d/screenshots/final.png)
- [recovery/0584bc159c734f4698c5c031b54faa16/screenshots/final.png](recovery/0584bc159c734f4698c5c031b54faa16/screenshots/final.png)
- [handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/confirm_open_account.png](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/confirm_open_account.png)
- [handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/final.png](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/final.png)
- [handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/handback_1_1.png](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/handback_1_1.png)
- [handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/handback_2_2.png](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/handback_2_2.png)
- [evals/c812dfc3de4c41248f5f6c279a228b2a/runs/1f7ac620e5d346619e89d38c41be8d75/screenshots/final.png](evals/c812dfc3de4c41248f5f6c279a228b2a/runs/1f7ac620e5d346619e89d38c41be8d75/screenshots/final.png)
- [evals/c812dfc3de4c41248f5f6c279a228b2a/runs/ff6d196b6c604d1488e28a6dfd28fd3f/screenshots/final.png](evals/c812dfc3de4c41248f5f6c279a228b2a/runs/ff6d196b6c604d1488e28a6dfd28fd3f/screenshots/final.png)
- [evals/c812dfc3de4c41248f5f6c279a228b2a/runs/2433b7987b7c46209d34733fdf5f427a/screenshots/final.png](evals/c812dfc3de4c41248f5f6c279a228b2a/runs/2433b7987b7c46209d34733fdf5f427a/screenshots/final.png)
- [evals/c812dfc3de4c41248f5f6c279a228b2a/runs/7253e0fb8a714186962d2d0e49a493ef/screenshots/final.png](evals/c812dfc3de4c41248f5f6c279a228b2a/runs/7253e0fb8a714186962d2d0e49a493ef/screenshots/final.png)
- [evals/c812dfc3de4c41248f5f6c279a228b2a/runs/dd13efe32da84d21a0afb1024111ace2/screenshots/final.png](evals/c812dfc3de4c41248f5f6c279a228b2a/runs/dd13efe32da84d21a0afb1024111ace2/screenshots/final.png)
- [handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/search_member.png](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/search_member.png)

- [Supervisor notice before handoff](handoff/cf9eee0ef2d84e818f359364ba36ac54/screenshots/handoff_1.png)

## Cleanup selection

The original archive manifest remains unchanged. These aggregate reports are intentionally excluded because their command strings contain machine-specific absolute paths: `checks.json`, `initial-run-index.md`, `report.json`, `reviewed-report.json`. Component run records remain unchanged and their hashes can be checked against the manifest. Omitted entries are not missing successful-run evidence. Use the [submission evidence map](../../README.md) and [current verification](../../../docs/cleanup.md).

The `search_member.png` and failed-provider `3.png` examples above are intentional FULL_MASK fallback captures. Their adjacent manifests record `fallback_full_mask=true`; all-black pixels demonstrate fail-closed privacy when selective coverage could not be certified.
