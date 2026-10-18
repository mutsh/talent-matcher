"""Deterministic eligibility engine: talent x program -> status + reasons.

Design choices:
- Rules are data (programs.json), this file only knows a few generic operators.
  Adding a program never needs new code.
- Three-valued logic: a rule passes, fails, or cannot be evaluated (missing data).
  Missing data goes to a human; it is never treated as a silent "no".
- No AI here on purpose: legal eligibility must be reproducible and auditable.
"""
from __future__ import annotations

from typing import Any

from .models import CEFR_ORDER, EligibilityResult, Program, Rule, RuleResult, Status, Talent

_MISSING = object()


def _get(talent: Talent, dotted: str) -> Any:
    """Read a dotted path such as 'education.eqf_level' or 'languages.en'."""
    obj: Any = talent
    for part in dotted.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part, _MISSING)
        else:
            obj = getattr(obj, part, _MISSING)
        if obj is _MISSING or obj is None:
            return _MISSING
    return obj


def evaluate_rule(talent: Talent, rule: Rule, program: Program) -> RuleResult:
    actual = _get(talent, rule.field)
    if actual is _MISSING:
        return RuleResult(rule_id=rule.id, passed=None,
                          reason=f"Cannot check: '{rule.field}' is missing from the profile. Rule: {rule.text}.")

    if rule.op == "in":
        ok = str(actual).lower() in [v.lower() for v in rule.value]
        detail = f"field is '{actual}'"
    elif rule.op == "in_program_occupations":
        ok = str(actual).lower() in [o.lower() for o in program.occupations]
        detail = f"occupation is '{actual}'"
    elif rule.op == ">=":
        ok = float(actual) >= float(rule.value)
        detail = f"has {actual}, needs {rule.value}"
    elif rule.op == "cefr>=":
        if actual not in CEFR_ORDER:
            return RuleResult(rule_id=rule.id, passed=None,
                              reason=f"Cannot check: language level '{actual}' is not a CEFR level.")
        ok = CEFR_ORDER.index(actual) >= CEFR_ORDER.index(rule.value)
        detail = f"has {actual}, needs {rule.value}"
    else:  # pragma: no cover - guarded by the Literal type in models.py
        raise ValueError(f"Unknown operator {rule.op}")

    return RuleResult(rule_id=rule.id, passed=ok,
                      reason=f"{'Meets' if ok else 'Does not meet'}: {rule.text} ({detail}).")


def check_eligibility(talent: Talent, program: Program) -> EligibilityResult:
    results = [evaluate_rule(talent, r, program) for r in program.rules]
    missing_docs = [d for d in program.required_documents if d not in talent.documents]

    if any(r.passed is False for r in results):
        status = Status.NOT_ELIGIBLE        # a hard fail always wins
    elif any(r.passed is None for r in results):
        status = Status.UNKNOWN             # route to a recruiter, don't reject
    elif missing_docs:
        status = Status.PENDING_DOCS        # eligible, actionable gap
    else:
        status = Status.ELIGIBLE

    return EligibilityResult(talent_id=talent.id, program_id=program.id,
                             program_version=program.version, status=status,
                             rule_results=results, missing_documents=missing_docs)


def eligibility_matrix(talents: list[Talent], programs: list[Program]) -> dict[tuple[str, str], EligibilityResult]:
    return {(t.id, p.id): check_eligibility(t, p) for t in talents for p in programs}
