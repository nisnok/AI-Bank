"""Trusted simulator handoff contract. Does not modify the replay artifact."""
from deterministic_ui.handoff import OperatorAction, ResumePlan
from deterministic_ui.models import Accessibility, Condition, Expectation, SemanticTarget


def target(concept, role, name):
    return SemanticTarget(concept=concept, strategies=[Accessibility(role=role, name=name)])


def condition(name, role, label, value=None):
    return Condition(id=name, target=target(name, role, label),
                     expected=Expectation(kind="text_equals", value=value) if value else Expectation())


def savings_plans():
    identity = condition("handoff_member_verified", "status", "Loaded member identifier", "{{ inputs.member_id }}")
    review = condition("handoff_review", "region", "Account opening review")
    deposit = condition("handoff_deposit_verified", "status", "Review initial deposit", "{{ inputs.initial_deposit }}")
    opened = condition("handoff_account_opened", "region", "Account opened")
    posted = condition("handoff_posted_deposit", "status", "Posted initial deposit", "{{ inputs.initial_deposit }}")
    acknowledged = Condition(id="notice_dismissed", target=target("supervisor_notice", "dialog", "Unexpected terminal notice"),
                             expected=Expectation(kind="absent"))
    return {
        "verify_member": ResumePlan(retry=[identity, acknowledged], actions=[
            OperatorAction(id="acknowledge_notice", label="Acknowledge supervisor notice",
                           target=target("acknowledge_notice", "button", "Acknowledge supervisor notice"),
                           postconditions=[acknowledged])]),
        "confirm_open_account": ResumePlan(completed=[opened, identity, posted], actions=[
            OperatorAction(id="confirm_account", label="Confirm / Open Account — posts deposit",
                           target=target("confirm_account", "button", "Confirm / Open Account"),
                           irreversible=True, preconditions=[identity, review, deposit],
                           postconditions=[opened, identity, posted])]),
    }
