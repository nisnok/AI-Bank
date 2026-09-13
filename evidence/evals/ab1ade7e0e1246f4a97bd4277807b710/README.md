# Automated evaluation and failure analysis

Canonical capability: get_member_balance@1.0.0

[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)

| Scenario | Actual status | Failure classification | Expectation met | Run |
|---|---|---|---|---|
| happy_path | SUCCESS | none | True | [067df8c2f4ee4d1aad22719321642a6e](runs/067df8c2f4ee4d1aad22719321642a6e/result.json) |
| primary_failure_fallback_success | SUCCESS | none | True | [9ba9a6f237f240fe8a527014363058fd](runs/9ba9a6f237f240fe8a527014363058fd/result.json) |
| all_locators_failed | RECOVERABLE_ERROR | POSTCONDITION_FAILED | False | [dc378d5bebfa4dc8a4e051dca2f0e617](runs/dc378d5bebfa4dc8a4e051dca2f0e617/result.json) |
| required_element_missing | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | True | [0f42a03e757f49ab8eaa1d6ce12f0648](runs/0f42a03e757f49ab8eaa1d6ce12f0648/result.json) |
| stale_member | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [950bcf68004c4dcaba86815f6dad9ca7](runs/950bcf68004c4dcaba86815f6dad9ca7/result.json) |
| partial_page_load | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [8279612d60cf4f17bb68ac0178483755](runs/8279612d60cf4f17bb68ac0178483755/result.json) |
| tenant_baseline | SUCCESS | none | True | [9510cb6b4714424f96774aa5ba8d3b3c](runs/9510cb6b4714424f96774aa5ba8d3b3c/result.json) |
| tenant_label_drift | SUCCESS | none | True | [3fd53148f72e489a82a972fb370d6442](runs/3fd53148f72e489a82a972fb370d6442/result.json) |
| tenant_structural_drift | SUCCESS | none | True | [253ea2f9257b40fbb5b6523533f4c986](runs/253ea2f9257b40fbb5b6523533f4c986/result.json) |
| ambiguous_control | HUMAN_REQUIRED | AMBIGUOUS_TARGET | True | [8646d575882c4aafbd9ce70828d38f69](runs/8646d575882c4aafbd9ce70828d38f69/result.json) |
| value_not_retained | RECOVERABLE_ERROR | POSTCONDITION_FAILED | True | [f6f5bc58ce0d4feda30e38f996e5434e](runs/f6f5bc58ce0d4feda30e38f996e5434e/result.json) |
| unexpected_workspace | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | False | [ed05f1b9d6804bff97e660b8f12a8cbc](runs/ed05f1b9d6804bff97e660b8f12a8cbc/result.json) |
| member_not_found | BUSINESS_OUTCOME | none | True | [660d31c34a0d41289a2a04e37baded48](runs/660d31c34a0d41289a2a04e37baded48/result.json) |
