"""Router signals: strong patterns must short-circuit correctly (no LLM here).

The patterns themselves live in the domain pack; these tests pin the loading
and precedence machinery, plus the behaviour the active pack promises.
"""

from app.router import route_by_signals


def test_comparison_goes_to_agent():
    decision = route_by_signals(
        "Compare the obligations of a provider and a deployer of a high-risk AI system."
    )
    assert decision is not None
    assert decision.path == "agent"
    assert decision.escalate is False


def test_annex_lookup_escalates():
    decision = route_by_signals("Which systems does Annex III list as high-risk?")
    assert decision is not None
    assert decision.path == "agent"
    assert decision.escalate is True


def test_penalties_escalate():
    decision = route_by_signals("What administrative fines apply to a prohibited practice?")
    assert decision is not None
    assert decision.escalate is True


def test_planning_goes_to_agent():
    decision = route_by_signals(
        "Give me a step-by-step compliance plan for deploying a high-risk system."
    )
    assert decision is not None
    assert decision.path == "agent"


def test_signals_are_language_agnostic():
    """EU corpora get queried in more than one language; the signals follow."""
    decision = route_by_signals("Confronta gli obblighi del fornitore e del deployer.")
    assert decision is not None
    assert decision.path == "agent"


def test_simple_lookup_has_no_signal():
    assert route_by_signals("When does the AI Act enter into force?") is None
    assert route_by_signals("What is an 'AI system' under Article 3?") is None
    assert route_by_signals("Who must register in the EU database?") is None
