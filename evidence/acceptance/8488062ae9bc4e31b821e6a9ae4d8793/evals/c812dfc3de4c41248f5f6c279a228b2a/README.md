# Automated evaluation and failure analysis

Canonical capability: get_member_balance@1.0.0

[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)

| Scenario | Actual status | Failure classification | Expectation met | Run |
|---|---|---|---|---|
| happy_path | SUCCESS | none | True | [1f7ac620e5d346619e89d38c41be8d75](runs/1f7ac620e5d346619e89d38c41be8d75/result.json) |
| primary_failure_fallback_success | SUCCESS | none | True | [a7ada6c2d55b4add88adcb34ef5c3280](runs/a7ada6c2d55b4add88adcb34ef5c3280/result.json) |
| all_locators_failed | RECOVERABLE_ERROR | FALLBACK_EXHAUSTED | True | [ca47dbe9764849cb93556cd5426e7d5b](runs/ca47dbe9764849cb93556cd5426e7d5b/result.json) |
| required_element_missing | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | True | [ff6d196b6c604d1488e28a6dfd28fd3f](runs/ff6d196b6c604d1488e28a6dfd28fd3f/result.json) |
| stale_member | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [49db5af934a2480694226fcafb4ba444](runs/49db5af934a2480694226fcafb4ba444/result.json) |
| partial_page_load | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [2433b7987b7c46209d34733fdf5f427a](runs/2433b7987b7c46209d34733fdf5f427a/result.json) |
| tenant_baseline | SUCCESS | none | True | [eda13816703940fa83909e708ed954a7](runs/eda13816703940fa83909e708ed954a7/result.json) |
| tenant_label_drift | SUCCESS | none | True | [7253e0fb8a714186962d2d0e49a493ef](runs/7253e0fb8a714186962d2d0e49a493ef/result.json) |
| tenant_structural_drift | SUCCESS | none | True | [f9ec2d02469e42e8a0fccab44cd91d31](runs/f9ec2d02469e42e8a0fccab44cd91d31/result.json) |
| ambiguous_control | HUMAN_REQUIRED | AMBIGUOUS_TARGET | True | [dd13efe32da84d21a0afb1024111ace2](runs/dd13efe32da84d21a0afb1024111ace2/result.json) |
| value_not_retained | RECOVERABLE_ERROR | POSTCONDITION_FAILED | True | [95c48124875c4ac3a383cc12ae6141fd](runs/95c48124875c4ac3a383cc12ae6141fd/result.json) |
| unexpected_workspace | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [7dcaf91f9d50470289e7c50285556d54](runs/7dcaf91f9d50470289e7c50285556d54/result.json) |
| member_not_found | BUSINESS_OUTCOME | none | True | [895e451c6af44ea786828256f488e575](runs/895e451c6af44ea786828256f488e575/result.json) |
