"""Skill normalisation: map free-text skills to canonical skills and compare them.

This is the one place where a learned model belongs in production:
replace the hand-written tables with ESCO skill codes plus an embedding
model (e.g. multilingual sentence embeddings) and a similarity threshold.
The interface `skill_similarity(required, has) -> 0..1` stays the same.
"""
from __future__ import annotations

# A skill the talent HAS -> the canonical skills it covers (one direction only:
# someone with "milking robots" can milk, but "milking" does not imply robots).
IMPLIES: dict[str, set[str]] = {
    "mig/mag welding": {"mig welding", "mag welding"},
    "gmaw": {"mig welding"},
    "milking robots": {"milking robots", "milking"},
    "cnc milling": {"cnc milling", "cnc machining"},
}

# Canonical pairs that are related but not the same skill -> partial credit.
RELATED: dict[frozenset[str], float] = {
    frozenset({"mig welding", "mag welding"}): 0.7,
    frozenset({"mig welding", "tig welding"}): 0.5,
    frozenset({"bread baking", "sourdough"}): 0.6,
}


def _norm(skill: str) -> str:
    return skill.strip().lower()


def skill_similarity(required: str, has: str) -> float:
    req = _norm(required)
    covered = IMPLIES.get(_norm(has), {_norm(has)})
    if req in covered:
        return 1.0
    return max((RELATED.get(frozenset({req, c}), 0.0) for c in covered), default=0.0)


def best_match(required: str, talent_skills: list[str]) -> tuple[float, str | None]:
    """Best similarity of one required skill against all talent skills, and which skill matched."""
    best, which = 0.0, None
    for s in talent_skills:
        sim = skill_similarity(required, s)
        if sim > best:
            best, which = sim, s
    return best, which
