import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from deterministic_ui.models import CapabilityArtifact, CapabilityLifecycle, Observation, Status
from fake_surface import FakeSurface
from tenant_reuse.binder import BindingError, TenantBindingResolver
from tenant_reuse.models import ObservedApplication, TenantBinding, TenantContext, digest
from tenant_reuse.runner import replay_tenant


CANONICAL = Path("capabilities/generated/get_member_balance/1.0.0/validated.json")


@pytest.fixture
def canonical():
    return CapabilityArtifact.model_validate_json(CANONICAL.read_text())


def binding(tenant):
    return TenantBinding.model_validate_json(Path(f"tenant_bindings/{tenant}/1.0.0.json").read_text())


def context(tenant):
    return TenantContext(tenant_id=tenant, display_name=tenant, base_url=f"http://127.0.0.1:8765/?tenant={tenant}",
                         product="legacy-bank-simulator", application_version="1")


def observed(tenant, version="1"):
    return ObservedApplication(tenant_id=tenant, product="legacy-bank-simulator", application_version=version)


class TenantFake(FakeSurface):
    def __init__(self, tenant="bank_b", drift="none", version="1"):
        super().__init__()
        self.tenant = tenant
        self.matches.clear()
        for label, token, value in (
            ("Institution identifier","institution",tenant),
            ("Application product","product","legacy-bank-simulator"),
            ("Application version","version",version)):
            self.set_match("accessibility", label, token)
            self.observations[token] = Observation(visible=True, text=value)
        label = "Customer Number" if tenant=="bank_b" else "Member ID"
        search = "Find Customer" if tenant=="bank_b" else "Search"
        if drift != "label":
            self.set_match("accessibility",label,"member")
            self.set_match("label",label,"member")
        self.set_match("css","#customer-reference" if tenant=="bank_b" else "#member-key","member")
        self.set_match("accessibility",search,*(["search","duplicate"] if drift=="ambiguous" else ["search"]))

    async def observe(self, target=None):
        if target and target.token=="member":
            return Observation(visible=True,value=self.member_id)
        if target and target.token=="identity":
            return Observation(visible=True,text=self.member_id)
        return await super().observe(target)

    async def click(self, target, timeout_ms):
        self.actions.append(("click",target.token))
        if self.member_id == "99999":
            self.set_match("text","Customer not found" if self.tenant=="bank_b" else "Member not found","missing")
            self.observations["missing"] = Observation(visible=True)
            return
        self.set_match("accessibility","Loaded customer identifier" if self.tenant=="bank_b" else "Loaded member identifier","identity")
        self.set_match("accessibility","Available Savings" if self.tenant=="bank_b" else "Savings balance","balance")
        self.observations["balance"] = Observation(visible=True,text="807.20")


@pytest.mark.parametrize("tenant", ["bank_a","bank_b"])
async def test_same_canonical_replays_both_tenants(canonical, tmp_path, tenant):
    original = canonical.model_dump_json()
    result = await replay_tenant(canonical, context(tenant), binding(tenant), TenantFake(tenant),
                                 {"member_id":"83921"}, evidence_root=tmp_path)
    assert result.status == Status.SUCCESS and result.model_calls == 0
    assert result.outputs["savings_balance"] == Decimal("807.20")
    assert canonical.model_dump_json() == original
    metadata = json.loads((tmp_path/result.run_id/"metadata.json").read_text())
    assert metadata["tenant_id"] == tenant and metadata["binding_version"] == "1.0.0"
    assert metadata["canonical_digest"] == digest(canonical)
    assert metadata["observed_application_version"] == "1"


def test_binding_changes_only_locators(canonical):
    effective = TenantBindingResolver().bind(canonical,context("bank_b"),binding("bank_b"),observed("bank_b"))
    assert effective.artifact.capability_id == canonical.capability_id
    assert effective.artifact.capability_version == canonical.capability_version
    assert effective.artifact.inputs == canonical.inputs and effective.artifact.outputs == canonical.outputs
    assert effective.artifact.safety == canonical.safety
    assert effective.artifact.lifecycle == canonical.lifecycle and effective.artifact.provenance == canonical.provenance
    assert [s.id for s in effective.artifact.steps] == [s.id for s in canonical.steps]
    assert [s.action for s in effective.artifact.steps] == [s.action for s in canonical.steps]
    assert [s.risk for s in effective.artifact.steps] == [s.risk for s in canonical.steps]
    assert effective.artifact.steps[0].target.strategies[0].model_dump()["name"] == "Customer Number"
    assert effective.artifact.steps[0].input == "{{ inputs.member_id }}"
    assert effective.artifact.success.expected == canonical.success.expected
    assert effective.artifact.steps[0].postcondition is not None
    assert effective.artifact.steps[0].postcondition.expected == canonical.steps[0].postcondition.expected


@pytest.mark.parametrize("field,value", [
    ("action","click"), ("steps",[]), ("step_order",["discovered_3","discovered_1"]),
    ("inputs",{"member_id":{"type":"integer"}}), ("outputs",{"savings_balance":{"type":"string"}}),
    ("risk","READ"), ("safety",{"approved_for_replay":True}), ("policy",{"IRREVERSIBLE":"ALLOW"}),
    ("lifecycle","VALIDATED"), ("success",{"expected":{"kind":"absent"}})])
def test_binding_rejects_protected_fields(field,value):
    data = binding("bank_b").model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        TenantBinding.model_validate(data)


@pytest.mark.parametrize("field", ["action","risk","input","output","precondition","postcondition"])
def test_target_override_cannot_hide_semantic_changes(field):
    data = binding("bank_b").model_dump()
    data["targets"][0][field] = "override"
    with pytest.raises(ValidationError):
        TenantBinding.model_validate(data)


def test_missing_or_wrong_binding_fails_closed(canonical):
    resolver = TenantBindingResolver()
    with pytest.raises(BindingError,match="TENANT_BINDING_REQUIRED"):
        resolver.bind(canonical,context("bank_b"),None,observed("bank_b"))
    with pytest.raises(BindingError,match="TENANT_MISMATCH"):
        resolver.bind(canonical,context("bank_b"),binding("bank_a"),observed("bank_b"))
    with pytest.raises(BindingError,match="CANONICAL_BINDING_MISMATCH"):
        resolver.bind(canonical,context("bank_b"),binding("bank_b").model_copy(update={"canonical_digest":"0"*64}),observed("bank_b"))
    with pytest.raises(BindingError,match="INCOMPATIBLE_APPLICATION_VERSION"):
        resolver.bind(canonical,context("bank_b"),binding("bank_b"),observed("bank_b","2"))
    with pytest.raises(BindingError,match="INCOMPATIBLE_PRODUCT"):
        resolver.bind(canonical,context("bank_b"),binding("bank_b"),observed("bank_b").model_copy(update={"product":"other"}))


def test_unknown_and_duplicate_targets_rejected(canonical):
    data = binding("bank_b").model_dump()
    data["targets"][0]["canonical_target"]["concept"] = "unknown"
    with pytest.raises(BindingError,match="UNKNOWN_CANONICAL_TARGET"):
        TenantBindingResolver().bind(canonical,context("bank_b"),TenantBinding.model_validate(data),observed("bank_b"))
    data = binding("bank_b").model_dump()
    data["targets"].append(data["targets"][0])
    with pytest.raises(BindingError,match="DUPLICATE_TARGET_BINDING"):
        TenantBindingResolver().bind(canonical,context("bank_b"),TenantBinding.model_validate(data),observed("bank_b"))


async def test_binding_cannot_approve_draft(canonical,tmp_path):
    draft = canonical.model_copy(update={"lifecycle":CapabilityLifecycle.DRAFT,
        "provenance":canonical.provenance.model_copy(update={"validation_run_id":None})})
    draft_binding = binding("bank_b").model_copy(update={"canonical_digest":digest(draft)})
    surface = TenantFake()
    result = await replay_tenant(draft,context("bank_b"),draft_binding,surface,{"member_id":"83921"},evidence_root=tmp_path)
    assert result.status == Status.HUMAN_REQUIRED and not surface.actions
    assert result.failure is not None
    assert result.failure.code == "DRAFT_REQUIRES_VALIDATION"


async def test_label_drift_fallback_succeeds_and_emits_signal(canonical,tmp_path):
    result = await replay_tenant(canonical,context("bank_b"),binding("bank_b"),TenantFake(drift="label"),
                                {"member_id":"83921"},evidence_root=tmp_path)
    assert result.status == Status.SUCCESS
    telemetry = json.loads((tmp_path/result.run_id/"locator-telemetry.json").read_text())
    signals = telemetry["drift_signals"]
    assert signals
    signal = next(s for s in signals if s["step_id"]=="discovered_1" and s["condition_id"] is None)
    assert signal["primary_strategy_succeeded"] is False
    assert signal["strategy_used"] == "css" and signal["fallback_depth"] == 2
    assert signal["match_count"] == 1 and signal["resolution_quality"] == "css_fallback"
    assert signal["execution_result"] == signal["step_execution_result"] == "SUCCESS"
    assert signal["recovery_needed"] and not signal["ambiguity"]


async def test_ambiguity_never_clicks(canonical,tmp_path):
    surface = TenantFake(drift="ambiguous")
    result = await replay_tenant(canonical,context("bank_b"),binding("bank_b"),surface,
                                {"member_id":"83921"},evidence_root=tmp_path)
    assert result.failure is not None
    assert result.status == Status.HUMAN_REQUIRED and result.failure.code == "AMBIGUOUS_TARGET"
    assert not any(action[0]=="click" for action in surface.actions)
    telemetry=json.loads((tmp_path/result.run_id/"locator-telemetry.json").read_text())
    assert any(s["ambiguity"] and s["match_count"]==2 and s["strategy_used"] is None for s in telemetry["drift_signals"])


async def test_business_outcome_stays_business_outcome(canonical,tmp_path):
    result = await replay_tenant(canonical,context("bank_b"),binding("bank_b"),TenantFake(),
                                {"member_id":"99999"},evidence_root=tmp_path)
    assert result.status == Status.BUSINESS_OUTCOME and result.business_code == "MEMBER_NOT_FOUND"


@pytest.mark.parametrize("missing,version,code", [(True,"1","TENANT_BINDING_REQUIRED"),
                                                (False,"2","INCOMPATIBLE_APPLICATION_VERSION")])
async def test_preflight_failure_has_evidence_and_no_actions(canonical,tmp_path,missing,version,code):
    surface=TenantFake(version=version)
    result=await replay_tenant(canonical,context("bank_b"),None if missing else binding("bank_b"),surface,
                               {"member_id":"83921"},evidence_root=tmp_path)
    assert result.failure is not None
    assert result.status == Status.HARD_FAILURE and result.failure.code == code
    assert not surface.actions and result.evidence_refs


def test_tenant_replay_has_no_model_browser_or_discovery_imports():
    for path in Path("src/tenant_reuse").glob("*.py"):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node,ast.Import) else (
                [node.module or ""] if isinstance(node,ast.ImportFrom) else [])
            assert not any(name.split(".")[0] in {"discovery","playwright","google","openai","anthropic"} for name in names)
    assert "bank_b" not in Path("src/deterministic_ui/replay.py").read_text()


@pytest.mark.parametrize("change", ["role","css_only","order"])
def test_binding_preserves_semantic_ladder(change):
    data=binding("bank_b").model_dump()
    strategies=data["targets"][0]["strategies"]
    if change=="role":
        strategies[0]["role"]="button"
    elif change=="css_only":
        data["targets"][0]["strategies"]=[strategies[-1]]
    else:
        data["targets"][0]["strategies"]=[strategies[1],strategies[0],strategies[2]]
    with pytest.raises(ValidationError):
        TenantBinding.model_validate(data)
