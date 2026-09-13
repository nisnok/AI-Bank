# Automated evaluation and failure analysis

Canonical capability: get_member_balance@1.0.0

[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)

| Scenario | Actual status | Failure classification | Expectation met | Run |
|---|---|---|---|---|
| happy_path | SUCCESS | none | True | [ee8b13921d3542ada680b4e9504f0a9b](runs/ee8b13921d3542ada680b4e9504f0a9b/result.json) |
| primary_failure_fallback_success | SUCCESS | none | True | [79c80b2eaa7f430eb190019bb43c3fc4](runs/79c80b2eaa7f430eb190019bb43c3fc4/result.json) |
| all_locators_failed | RECOVERABLE_ERROR | FALLBACK_EXHAUSTED | True | [489ae64d67db444ba0b52cafbbcce3a3](runs/489ae64d67db444ba0b52cafbbcce3a3/result.json) |
| required_element_missing | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | True | [430cad4d170245238baf79ac2775efb6](runs/430cad4d170245238baf79ac2775efb6/result.json) |
| stale_member | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [e4eeb25acaa046c4b234059efdbef362](runs/e4eeb25acaa046c4b234059efdbef362/result.json) |
| partial_page_load | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [222205c6ceb345d2a087bba2aa9c33ed](runs/222205c6ceb345d2a087bba2aa9c33ed/result.json) |
| tenant_baseline | SUCCESS | none | True | [35713d822bc54c21b8cceb5ab2627425](runs/35713d822bc54c21b8cceb5ab2627425/result.json) |
| tenant_label_drift | SUCCESS | none | True | [029ca54b70ab48869cc8cd2bbf9efeac](runs/029ca54b70ab48869cc8cd2bbf9efeac/result.json) |
| tenant_structural_drift | SUCCESS | none | True | [f92348fa642a4e1ab088a1233553771d](runs/f92348fa642a4e1ab088a1233553771d/result.json) |
| ambiguous_control | HUMAN_REQUIRED | AMBIGUOUS_TARGET | True | [cf5577f36ee4497d9de290f986244ae3](runs/cf5577f36ee4497d9de290f986244ae3/result.json) |
| value_not_retained | RECOVERABLE_ERROR | POSTCONDITION_FAILED | True | [c9d1edc735f04e33ad53e5e0c94d5f5d](runs/c9d1edc735f04e33ad53e5e0c94d5f5d/result.json) |
| unexpected_workspace | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | False | [f2b0e4f6f91a4fd88e6b6af6deb4ce09](runs/f2b0e4f6f91a4fd88e6b6af6deb4ce09/result.json) |
| member_not_found | BUSINESS_OUTCOME | none | True | [46d21843d1ca4f27ba59b62df0b96aaa](runs/46d21843d1ca4f27ba59b62df0b96aaa/result.json) |
