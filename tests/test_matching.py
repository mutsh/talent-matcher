from datetime import date
from pathlib import Path

import pytest

from matcher.eligibility import check_eligibility
from matcher.explain import _faithful
from matcher.models import Status, load_all
from matcher.ranking import applicable_programs, rank_for_order
from matcher.skills import skill_similarity

TODAY = date(2026, 10, 13)
T, P, O = load_all(Path(__file__).parents[1] / "data")
talent = {t.id: t for t in T}
program = {p.id: p for p in P}
order = {o.id: o for o in O}


def test_hard_fail_wins_over_missing_docs():
    r = check_eligibility(talent["T03"], program["DK-AGRI-TRAINEE"])  # 0.5y experience
    assert r.status == Status.NOT_ELIGIBLE
    assert any(rr.rule_id == "experience" and rr.passed is False for rr in r.rule_results)


def test_missing_data_goes_to_review_not_rejection():
    r = check_eligibility(talent["T04"], program["DK-AGRI-TRAINEE"])  # no English recorded
    assert r.status == Status.UNKNOWN


def test_missing_documents_is_actionable():
    r = check_eligibility(talent["T02"], program["DK-AGRI-TRAINEE"])
    assert r.status == Status.PENDING_DOCS and r.missing_documents == ["experience_letter"]


def test_order_routes_to_matching_program_only():
    assert [p.id for p in applicable_programs(order["O4"], P)] == ["NO-SKILLED-WORKER"]


def test_ranking_is_deterministic_and_relevant():
    _, s1, _ = rank_for_order(order["O2"], T, P, TODAY)
    _, s2, _ = rank_for_order(order["O2"], T, P, TODAY)
    assert [s.talent.id for s in s1] == [s.talent.id for s in s2] == ["T05", "T10", "T06"]


def test_late_candidate_is_flagged():
    _, sugg, _ = rank_for_order(order["O3"], T, P, TODAY)
    carlos = next(s for s in sugg if s.talent.id == "T07")
    assert not carlos.on_time


def test_every_suggestion_is_legally_eligible():
    for o in O:
        _, sugg, _ = rank_for_order(o, T, P, TODAY)
        assert all(s.eligibility.status in (Status.ELIGIBLE, Status.PENDING_DOCS) for s in sugg)


def test_name_does_not_affect_score():
    t = talent["T05"].model_copy(update={"name": "Someone Else"})
    _, a, _ = rank_for_order(order["O2"], [talent["T05"]], P, TODAY)
    _, b, _ = rank_for_order(order["O2"], [t], P, TODAY)
    assert a[0].score == b[0].score


@pytest.mark.parametrize("req,has,expected", [
    ("MIG welding", "MIG/MAG welding", 1.0),
    ("milking", "milking robots", 1.0),
    ("milking robots", "milking", 0.0),   # implication is one-directional
])
def test_skill_similarity(req, has, expected):
    assert skill_similarity(req, has) == expected


def test_llm_faithfulness_guard_rejects_new_numbers():
    assert _faithful("scores 90/100, 3 years", "Strong fit with 3 years")
    assert not _faithful("scores 90/100, 3 years", "Strong fit with 5 years")


def test_flags_candidate_topping_several_orders():
    from matcher.ranking import competing_orders, top_picks_by_order
    picks = top_picks_by_order(O, T, P, TODAY)
    assert "T05" in picks["O2"] and "T05" in picks["O4"]            # Ravi tops both welder orders
    assert competing_orders("T05", "O2", picks) == ["O4"]
    assert competing_orders("T01", "O1", picks) == []
