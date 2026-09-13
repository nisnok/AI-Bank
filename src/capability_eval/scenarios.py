from deterministic_ui.models import Status
from .models import FailureCode as F, Scenario


SCENARIOS = [
    Scenario(id="happy_path"),
    Scenario(id="primary_failure_fallback_success",drift="label"),
    Scenario(id="all_locators_failed",fault="ALL_LOCATORS_FAILED",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.FALLBACK_EXHAUSTED),
    Scenario(id="required_element_missing",fault="REQUIRED_ELEMENT_MISSING",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.REQUIRED_ELEMENT_MISSING),
    Scenario(id="stale_member",fault="STALE_MEMBER",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.PAGE_STATE_INVALID),
    Scenario(id="partial_page_load",fault="PARTIAL_PAGE",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.PAGE_STATE_INVALID),
    Scenario(id="tenant_baseline",tenant_id="bank_b"),
    Scenario(id="tenant_label_drift",tenant_id="bank_b",drift="label"),
    Scenario(id="tenant_structural_drift",tenant_id="bank_b",drift="structural"),
    Scenario(id="ambiguous_control",tenant_id="bank_b",drift="ambiguous",expected_status=Status.HUMAN_REQUIRED,expected_failure=F.AMBIGUOUS_TARGET),
    Scenario(id="value_not_retained",fault="VALUE_NOT_RETAINED",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.POSTCONDITION_FAILED),
    Scenario(id="unexpected_workspace",fault="UNEXPECTED_PAGE",expected_status=Status.RECOVERABLE_ERROR,expected_failure=F.PAGE_STATE_INVALID),
    Scenario(id="member_not_found",member_id="99999",expected_balance=None,expected_status=Status.BUSINESS_OUTCOME),
]
