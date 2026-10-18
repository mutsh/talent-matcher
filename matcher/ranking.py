"""Order -> applicable programs -> eligible talent -> transparent score -> ranked suggestions.

Two kinds of requirement, kept separate on purpose:
- Program rules (legal): decided in eligibility.py, never overridden by a score.
- Employer must-haves (min experience, min English): hard filters with a stated reason.
Everything else is a weighted score whose every point is explained.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .eligibility import check_eligibility
from .models import CEFR_ORDER, EligibilityResult, Order, Program, ScoreComponent, Status, Suggestion, Talent
from .skills import best_match

# Visible, tunable weights (sum = 100). In production: tuned against recruiter decisions.
WEIGHTS = {
    "required_skills": 40,
    "nice_to_have_skills": 10,
    "occupation": 10,
    "experience": 15,
    "english": 5,
    "documents": 10,
    "timeline": 10,
}
DOC_COLLECTION_WEEKS = 3   # assumed time to collect a missing document before applying


@dataclass
class Excluded:
    talent: Talent
    reason: str


def applicable_programs(order: Order, programs: list[Program]) -> list[Program]:
    """A program can serve an order if country, sector and occupation all fit."""
    return [p for p in programs
            if p.country == order.country
            and order.sector in p.sectors
            and order.occupation.lower() in [o.lower() for o in p.occupations]]


def earliest_start(talent: Talent, program: Program, elig: EligibilityResult, today: date) -> date:
    submit = today + timedelta(weeks=DOC_COLLECTION_WEEKS if elig.missing_documents else 0)
    permit_ready = submit + timedelta(weeks=program.processing_weeks)
    # Availability not stated -> assume the permit date (shown in the timeline reason)
    return max(talent.available_from or permit_ready, permit_ready)


def _same_occupation(talent: Talent, order: Order) -> bool:
    return (talent.occupation or "").lower() == order.occupation.lower()


def _cefr(level: str | None) -> int:
    return CEFR_ORDER.index(level) if level in CEFR_ORDER else -1


def score(talent: Talent, order: Order, program: Program, elig: EligibilityResult,
          start: date) -> list[ScoreComponent]:
    comps: list[ScoreComponent] = []

    # Required skills: average best match per required skill
    matches = [(req, *best_match(req, talent.skills)) for req in order.required_skills]
    frac = sum(m[1] for m in matches) / len(matches) if matches else 1.0
    parts = [f"{req}: {'full' if s == 1 else 'partial' if s > 0 else 'no'} match"
             + (f" via '{w}'" if w and s < 1 else "") for req, s, w in matches]
    comps.append(ScoreComponent(name="Required skills", points=WEIGHTS["required_skills"] * frac,
                                max_points=WEIGHTS["required_skills"], reason="; ".join(parts)))

    # Nice-to-have skills
    nice = [(n, *best_match(n, talent.skills)) for n in order.nice_to_have_skills]
    nfrac = sum(m[1] for m in nice) / len(nice) if nice else 0.0
    hit = [n for n, s, _ in nice if s >= 0.5]
    comps.append(ScoreComponent(name="Nice-to-have skills", points=WEIGHTS["nice_to_have_skills"] * nfrac,
                                max_points=WEIGHTS["nice_to_have_skills"],
                                reason=f"has {', '.join(hit)}" if hit else "none of the extras"))

    # Occupation
    same = _same_occupation(talent, order)
    comps.append(ScoreComponent(name="Occupation", points=WEIGHTS["occupation"] if same else 0,
                                max_points=WEIGHTS["occupation"],
                                reason=f"trained as {talent.occupation or 'not stated'}"
                                + ("" if same else f", order is for {order.occupation}")))

    # Experience: full points at twice the employer minimum (at least 2 years)
    target = max(2 * order.min_experience_years, 2)
    efrac = min(1.0, talent.relevant_experience_years / target)
    comps.append(ScoreComponent(name="Experience", points=WEIGHTS["experience"] * efrac,
                                max_points=WEIGHTS["experience"],
                                reason=f"{talent.relevant_experience_years:g} years "
                                       f"(employer minimum {order.min_experience_years:g})"))

    # English: meeting the minimum earns 2/3, one CEFR step above earns full points
    lvl = talent.languages.get("en")
    steps = _cefr(lvl) - _cefr(order.min_english)
    lfrac = max(0.0, min(1.0, (steps + 2) / 3))
    comps.append(ScoreComponent(name="English", points=WEIGHTS["english"] * lfrac,
                                max_points=WEIGHTS["english"],
                                reason=f"{lvl} (employer minimum {order.min_english})"))

    # Documents
    req_docs = program.required_documents
    have = len(req_docs) - len(elig.missing_documents)
    comps.append(ScoreComponent(name="Documents", points=WEIGHTS["documents"] * have / len(req_docs),
                                max_points=WEIGHTS["documents"],
                                reason="all documents in place" if not elig.missing_documents
                                else "missing " + ", ".join(elig.missing_documents)))

    # Timeline
    on_time = start <= order.start_date
    late_days = (start - order.start_date).days
    comps.append(ScoreComponent(name="Timeline", points=WEIGHTS["timeline"] if on_time else 0,
                                max_points=WEIGHTS["timeline"],
                                reason=f"can start {start.isoformat()}, employer needs {order.start_date.isoformat()}"
                                       + ("" if on_time else f" ({late_days} days late)")
                                       + ("" if talent.available_from else "; personal availability not stated")))
    return comps


def rank_for_order(order: Order, talents: list[Talent], programs: list[Program],
                   today: date) -> tuple[list[Program], list[Suggestion], list[Excluded]]:
    progs = applicable_programs(order, programs)
    suggestions: list[Suggestion] = []
    excluded: list[Excluded] = []

    if not progs:
        return progs, suggestions, [Excluded(t, "No program covers this order's country, sector and occupation")
                                    for t in talents]

    for t in talents:
        # 1) Legal eligibility under any applicable program; keep the best option
        options = []
        for p in progs:
            e = check_eligibility(t, p)
            if e.status in (Status.ELIGIBLE, Status.PENDING_DOCS):
                options.append((earliest_start(t, p, e, today), p, e))
        if not options:
            results = [check_eligibility(t, p) for p in progs]
            if any(r.status == Status.UNKNOWN for r in results):
                missing = {rr.reason for r in results for rr in r.rule_results if rr.passed is None}
                excluded.append(Excluded(t, "Needs recruiter review: " + " ".join(sorted(missing))))
            else:
                fails = {rr.reason for r in results for rr in r.rule_results if rr.passed is False}
                excluded.append(Excluded(t, "Not eligible: " + " ".join(sorted(fails))))
            continue
        start, prog, elig = min(options, key=lambda o: o[0])

        # 2) Employer must-haves
        if t.relevant_experience_years is None:
            excluded.append(Excluded(t, "Needs recruiter review: years of experience not stated"))
            continue
        if t.languages.get("en") not in CEFR_ORDER:
            excluded.append(Excluded(t, "Needs recruiter review: English level not stated as a CEFR level"))
            continue
        if t.relevant_experience_years < order.min_experience_years:
            excluded.append(Excluded(t, f"Below employer minimum experience "
                                        f"({t.relevant_experience_years:g} < {order.min_experience_years:g} years)"))
            continue
        if _cefr(t.languages.get("en")) < _cefr(order.min_english):
            excluded.append(Excluded(t, f"Below employer minimum English ({t.languages.get('en')} < {order.min_english})"))
            continue

        # 3) Transparent score
        comps = score(t, order, prog, elig, start)

        # 4) Relevance gate: a different trade with under half the required skills is noise, not a suggestion
        req = comps[0]
        if not _same_occupation(t, order) and req.points / req.max_points < 0.5:
            excluded.append(Excluded(t, f"Legally eligible, but trained as {t.occupation} and matches "
                                        f"under half of the required skills ({req.reason})"))
            continue
        suggestions.append(Suggestion(talent=t, program_id=prog.id, program_name=prog.name, eligibility=elig,
                                      score=round(sum(c.points for c in comps), 1), components=comps,
                                      earliest_start=start, on_time=start <= order.start_date))

    suggestions.sort(key=lambda s: (-s.score, s.earliest_start, s.talent.id))  # deterministic ties
    return progs, suggestions, excluded


def top_picks_by_order(orders: list[Order], talents: list[Talent], programs: list[Program],
                       today: date) -> dict[str, list[str]]:
    """Talent ids that would fill each order's headcount. Used to flag one person topping several orders.

    This is a flag, not an allocation: deciding who goes where across competing orders
    (an assignment problem respecting headcount and preferences) is a deliberate next step.
    """
    return {o.id: [s.talent.id for s in rank_for_order(o, talents, programs, today)[1][:o.headcount]]
            for o in orders}


def competing_orders(talent_id: str, current_order_id: str, top_picks: dict[str, list[str]]) -> list[str]:
    return [oid for oid, ids in top_picks.items() if oid != current_order_id and talent_id in ids]
