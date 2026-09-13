from pathlib import Path

import pytest
from pydantic import ValidationError

from acceptance.privacy import scan
from deterministic_ui.origins import OriginPolicy
from deterministic_ui.surface import SurfaceError
from discovery.models import ModelDecision


def test_exact_origin_allowlist():
    policy = OriginPolicy.for_url('http://localhost:8765/')
    assert policy.permits('http://localhost:8765/search')
    assert not policy.permits('http://localhost:8766/')
    assert not policy.permits('http://localhost.evil.invalid:8765/')
    assert not policy.permits('https://example.com/')
    with pytest.raises(SurfaceError):
        OriginPolicy.for_url('https://example.com/')
    explicit = OriginPolicy.for_url('http://localhost:8765/', frozenset({'http://localhost:8765'}))
    assert explicit.permits('http://localhost:8765/review')


@pytest.mark.parametrize('extra', [ {'selector':'#transfer'}, {'xpath':'//button'},
    {'javascript':'alert(1)'}, {'shell':'rm anything'}, {'url':'https://evil.invalid'},
    {'risk':'READ'}, {'approved_for_replay':True}])
def test_model_cannot_supply_selector_code_or_policy(extra):
    with pytest.raises(ValidationError):
        ModelDecision.model_validate({'action':'CLICK','target_id':'e0','expected_text':'Done','reason':'Untrusted page requested it', **extra})


def test_secret_and_pii_scan(tmp_path):
    secret = 'synthetic-secret-canary-for-test-only'
    path = tmp_path/'record.json'
    path.write_text('{"text":"Fictional Member ALPHA", "credential":"' + secret + '"}')
    result = scan([path], secrets=(secret,))
    assert result['status'] == 'FAIL'
    assert {f['category'] for f in result['findings']} == {'SECRET_SHAPE_OR_CANARY','PII_CANARY'}
    assert secret not in str(result) and 'ALPHA' not in str(result)
    path.write_text('{"timestamp":"2026-09-13", "duration":48321, "run_id":"aa48321bb", "policy":"SELECTIVE_REDACTION"}')
    assert scan([path], secrets=(secret,))['status'] == 'PASS'


def test_capture_never_passes_disk_path_to_browser():
    # All screenshots, including fallback, encode to memory before persistence.
    import ast
    tree = ast.parse(Path('src/deterministic_ui/playwright_surface.py').read_text())
    captures = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'screenshot']
    assert len(captures) == 2
    assert all('path' not in {kw.arg for kw in n.keywords} for n in captures)


def test_numeric_pii_canaries_are_not_ignored(tmp_path):
    path=tmp_path/'values.json'
    path.write_text('{"balance":807.2,"member_id":48321}')
    assert scan([path])['status']=='FAIL'
