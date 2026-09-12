import pytest

from deterministic_ui.models import Decision, MatchSet, Risk
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.resolver import LocatorResolver


async def test_ordered_fallback(artifact, surface):
    surface.matches.clear()
    surface.set_match("label", "Member Number", "member")
    result = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    assert result.succeeded and result.strategy == "label" and result.quality == "semantic"
    assert [a.matches for a in result.attempts] == [0, 1]
    assert len(surface.queries) == 2


async def test_ambiguity_stops_before_fallback(artifact, surface):
    surface.set_match("accessibility", "Member ID", "a", "b")
    result = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    assert result.code == "AMBIGUOUS_TARGET" and result.target is None
    assert result.matches == 2 and len(surface.queries) == 1


async def test_zero_match(artifact, surface):
    surface.matches.clear()
    result = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    assert result.code == "NO_TARGET" and len(result.attempts) == 3


async def test_relative_ambiguous_scope(artifact, surface):
    surface.matches[("relative", "Savings balance")] = MatchSet(ambiguous_scope=True)
    result = await LocatorResolver().resolve(artifact.steps[2].target, surface)
    assert result.code == "AMBIGUOUS_TARGET"
    assert result.attempts[-1].diagnostic == "ambiguous_scope"


@pytest.mark.parametrize('risk,decision', [(Risk.READ,Decision.ALLOW), (Risk.REVERSIBLE_WRITE,Decision.ALLOW),
    (Risk.SENSITIVE,Decision.REQUIRE_HUMAN), (Risk.IRREVERSIBLE,Decision.BLOCK)])
async def test_policy(artifact, surface, risk, decision):
    resolved = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    artifact = artifact.model_copy(update={"safety": artifact.safety.model_copy(update={"max_risk":Risk.IRREVERSIBLE})})
    step = artifact.steps[1].model_copy(update={"risk":risk})
    assert PolicyEngine().evaluate(artifact, step, resolved).decision == decision


async def test_css_fallback_allowed(artifact, surface):
    surface.matches.clear()
    surface.set_match("css", "#member-id", "member")
    resolved = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    assert resolved.quality == "css_fallback"
    assert PolicyEngine().evaluate(artifact, artifact.steps[0], resolved).decision == Decision.ALLOW


async def test_unapproved_and_max_risk(artifact, surface):
    resolved = await LocatorResolver().resolve(artifact.steps[0].target, surface)
    unapproved = artifact.model_copy(update={"safety":artifact.safety.model_copy(update={"approved_for_replay":False})})
    assert PolicyEngine().evaluate(unapproved, artifact.steps[0], resolved).decision == Decision.REQUIRE_HUMAN
    limited = artifact.model_copy(update={"safety":artifact.safety.model_copy(update={"max_risk":Risk.READ})})
    assert PolicyEngine().evaluate(limited, artifact.steps[0], resolved).decision == Decision.BLOCK
    assert PolicyEngine(PolicyConfig(decisions={})).evaluate(artifact, artifact.steps[0], resolved).decision == Decision.BLOCK
