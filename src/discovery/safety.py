"""Trusted operation classification and completion checks; no model-provided risk."""
from deterministic_ui.models import ObservedElement, Observation, Risk
from .models import DiscoveryAction


def classify(action: DiscoveryAction, element: ObservedElement) -> Risk:
    if action == DiscoveryAction.EXTRACT:
        return Risk.READ
    if action in {DiscoveryAction.FILL, DiscoveryAction.SELECT}:
        return Risk.REVERSIBLE_WRITE if element.name in {"Member ID", "Member Number"} else Risk.SENSITIVE
    if element.name == "Search" and element.role == "button":
        return Risk.READ
    if any(word in element.name.lower() for word in ("confirm", "delete", "transfer", "open account")):
        return Risk.IRREVERSIBLE
    return Risk.SENSITIVE


def member_matches(observation: Observation, member_id: str) -> bool:
    candidates = [el for el in observation.elements if el.name == "Loaded member identifier" and el.visible]
    return len(candidates) == 1 and candidates[0].text.strip() == member_id


def business_outcome(observation: Observation) -> str | None:
    messages = {"Member not found": "MEMBER_NOT_FOUND",
                "Member is not eligible for a new savings sub-account": "MEMBER_INELIGIBLE"}
    for element in observation.elements:
        if element.role == 'alert' and element.text in messages:
            return messages[element.text]
    return None
