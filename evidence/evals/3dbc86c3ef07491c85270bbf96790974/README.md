# Automated evaluation and failure analysis

Canonical capability: get_member_balance@1.0.0

[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)

| Scenario | Actual status | Failure classification | Expectation met | Run |
|---|---|---|---|---|
| happy_path | SUCCESS | none | True | [e12a2d9681cd495883d2a72e87e44a69](runs/e12a2d9681cd495883d2a72e87e44a69/result.json) |
| primary_failure_fallback_success | SUCCESS | none | True | [a6d15702f9e94a58b036303f8d739862](runs/a6d15702f9e94a58b036303f8d739862/result.json) |
| all_locators_failed | RECOVERABLE_ERROR | FALLBACK_EXHAUSTED | True | [f6aca15abc2a4c8cad78814365efbf45](runs/f6aca15abc2a4c8cad78814365efbf45/result.json) |
| required_element_missing | RECOVERABLE_ERROR | REQUIRED_ELEMENT_MISSING | True | [ca6cb2becabb4bccbb3153a2086a027b](runs/ca6cb2becabb4bccbb3153a2086a027b/result.json) |
| stale_member | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [ce26c6b9cd044d8f9c2ccbebe4e09ce5](runs/ce26c6b9cd044d8f9c2ccbebe4e09ce5/result.json) |
| partial_page_load | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [234976ea93e54a5c981475ee36586158](runs/234976ea93e54a5c981475ee36586158/result.json) |
| tenant_baseline | SUCCESS | none | True | [90603a3713bf447cb89fbc34df02944e](runs/90603a3713bf447cb89fbc34df02944e/result.json) |
| tenant_label_drift | SUCCESS | none | True | [2e17923ded7f4d54aa00debe1bf579da](runs/2e17923ded7f4d54aa00debe1bf579da/result.json) |
| tenant_structural_drift | SUCCESS | none | True | [ee9fcb0daefd49de928491ba038ba818](runs/ee9fcb0daefd49de928491ba038ba818/result.json) |
| ambiguous_control | HUMAN_REQUIRED | AMBIGUOUS_TARGET | True | [7b53c332691e494692abacf5ee894421](runs/7b53c332691e494692abacf5ee894421/result.json) |
| value_not_retained | RECOVERABLE_ERROR | POSTCONDITION_FAILED | True | [eb158c3fc5f440cab54064e6af735334](runs/eb158c3fc5f440cab54064e6af735334/result.json) |
| unexpected_workspace | RECOVERABLE_ERROR | PAGE_STATE_INVALID | True | [418f5178d9694a51a7ee7fe0c7c8fd0f](runs/418f5178d9694a51a7ee7fe0c7c8fd0f/result.json) |
| member_not_found | BUSINESS_OUTCOME | none | True | [9190842a3e7f478c918885319022c4d2](runs/9190842a3e7f478c918885319022c4d2/result.json) |
