"""Turn the decision trace into plain words.

Default: deterministic templates, so every sentence maps 1:1 to a rule or score component.
Optional: an LLM rewrites the template text for readability. It receives ONLY the trace,
is told not to add facts, and its output is rejected if it introduces numbers or dates
that are not in the trace (a cheap faithfulness check). Falls back to the template.
"""
from __future__ import annotations

import re

from .models import EligibilityResult, Order, Program, Status, Suggestion


def explain_eligibility(e: EligibilityResult, program: Program) -> str:
    lines = [f"{e.status.value} for {program.name} (rules v{e.program_version})."]
    lines += [f"- {r.reason}" for r in e.rule_results]
    if e.missing_documents and e.status != Status.NOT_ELIGIBLE:
        lines.append(f"- Still needed: {', '.join(e.missing_documents)}.")
    return "\n".join(lines)


def explain_suggestion(s: Suggestion, order: Order, rank: int) -> str:
    t = s.talent
    c = {x.name: x for x in s.components}
    skill_like = ("Required skills", "Nice-to-have skills", "Occupation", "Experience", "English")
    ratio = lambda x: x.points / x.max_points  # noqa: E731
    strengths = [x for x in sorted(s.components, key=ratio, reverse=True)
                 if x.name in skill_like and ratio(x) >= 0.7][:2]
    gaps = [x for x in s.components if x.name in skill_like and ratio(x) < 0.5]

    text = (f"#{rank} {t.name} ({t.id}) scores {s.score:g}/100 for {order.employer}. "
            f"Legally eligible under {s.program_name}.")
    if strengths:
        text += " Strongest points: " + " and ".join(f"{x.name.lower()} ({x.reason})" for x in strengths) + "."
    if gaps:
        text += " Gaps: " + "; ".join(f"{g.name.lower()} ({g.reason})" for g in gaps) + "."
    if s.eligibility.missing_documents:
        text += f" Action: collect {', '.join(s.eligibility.missing_documents)} before applying."
    text += (f" Timing: {c['Timeline'].reason}." if s.on_time
             else f" Timing risk: {c['Timeline'].reason}.")
    return text


# ---------- optional LLM polish ----------
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _faithful(source: str, rewritten: str) -> bool:
    """Every number in the rewrite must already appear in the source trace."""
    return set(_NUM.findall(rewritten)) <= set(_NUM.findall(source))


def polish_with_llm(text: str) -> tuple[str, bool]:
    """Returns (text, used_llm). No API key, an error, or an unfaithful rewrite -> template text unchanged."""
    from . import llm
    if not llm.available():
        return text, False
    try:
        out = llm.generate_text(
            system=("Rewrite the recruiter note in clear, friendly plain English for a recruiter. "
                    "Use ONLY facts in the note. Do not add, infer or change any fact, number or date. "
                    "Do not mention nationality, age, gender or other personal attributes. Max 3 sentences."),
            prompt=text, max_tokens=300)
        return (out, True) if out and _faithful(text, out) else (text, False)
    except Exception:
        return text, False
