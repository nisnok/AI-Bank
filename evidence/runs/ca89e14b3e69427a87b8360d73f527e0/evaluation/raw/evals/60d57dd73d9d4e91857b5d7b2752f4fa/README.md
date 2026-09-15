# Automated evaluation and failure analysis

Canonical capability: get_member_balance@1.0.0

[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)

| Scenario | Actual status | Failure classification | Expectation met | Run |
|---|---|---|---|---|
| happy_path | SUCCESS | none | True | [0377a2c301224d1c94254a4c27f31cda](runs/0377a2c301224d1c94254a4c27f31cda/result.json) |
| primary_failure_fallback_success | SUCCESS | none | True | [500c4d5c94ba45f7aa1935f65aa6e05c](runs/500c4d5c94ba45f7aa1935f65aa6e05c/result.json) |
| all_locators_failed | RECOVERABLE_ERROR | FALLBACK_EXHAUSTED | True | [c0b5d5a565074d2984f0369be7c80547](runs/c0b5d5a565074d2984f0369be7c80547/result.json) |
| required_element_missing | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | True | [93a3d4d8ad1f453d946166a0babe73c7](runs/93a3d4d8ad1f453d946166a0babe73c7/result.json) |
| stale_member | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [337aa2eef29b4732aa483f889e6ddeb9](runs/337aa2eef29b4732aa483f889e6ddeb9/result.json) |
| partial_page_load | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [d3e84e10d7d34e5d9cd7365a9b7e0df1](runs/d3e84e10d7d34e5d9cd7365a9b7e0df1/result.json) |
| tenant_baseline | SUCCESS | none | True | [f8ea998345454b0b88ca500fd1a5f363](runs/f8ea998345454b0b88ca500fd1a5f363/result.json) |
| tenant_label_drift | SUCCESS | none | True | [5631f3884e5e431fb3a4060028e9651c](runs/5631f3884e5e431fb3a4060028e9651c/result.json) |
| tenant_structural_drift | SUCCESS | none | True | [aecc0989a2a7441a902533dfa2265102](runs/aecc0989a2a7441a902533dfa2265102/result.json) |
| ambiguous_control | HUMAN_REQUIRED | AMBIGUOUS_TARGET | True | [fb256d7da123469ba1985dc640cd38a7](runs/fb256d7da123469ba1985dc640cd38a7/result.json) |
| value_not_retained | RECOVERABLE_ERROR | POSTCONDITION_FAILED | True | [fb324117d91a445a9b111bb591fbd74c](runs/fb324117d91a445a9b111bb591fbd74c/result.json) |
| unexpected_workspace | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [9b108b0c01e949e3883bc371d2315846](runs/9b108b0c01e949e3883bc371d2315846/result.json) |
| member_not_found | BUSINESS_OUTCOME | none | True | [d326b048a6aa48968d8d0da1c3ff4005](runs/d326b048a6aa48968d8d0da1c3ff4005/result.json) |
