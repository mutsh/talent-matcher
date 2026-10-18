"""Score extraction results against hand-labelled gold data.

What is measured, and why:
- Field accuracy for the values the rules engine uses (occupation, education field, EQF,
  experience, English, documents, availability). These decide eligibility, so they matter most.
- Recall of order-relevant skills: did the extractor find the skills that matter for matching?
- Unverified-evidence rate: share of extracted items whose quote is NOT in the document
  (a hallucination proxy; precision-like).
- Injection resistance: the planted CV must not inflate experience or English.
The scoring is deterministic and unit-tested; only the extraction itself calls the LLM.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .extraction import ExtractionResult, extract_talent
from .models import load_all
from .skills import skill_similarity

FIELDS = ["occupation", "education_field", "eqf_level", "experience_years", "english",
          "documents", "available_from"]


@dataclass
class CVScore:
    cv: str
    fields: dict[str, bool]
    got: dict[str, object]
    skills_found: list[str]
    skills_missed: list[str]
    evidence_total: int
    evidence_unverified: int
    injection_ok: bool | None = None
    seconds: float = 0.0
    error: str | None = None

    @property
    def field_accuracy(self) -> float:
        return sum(self.fields.values()) / len(self.fields) if self.fields else 0.0


@dataclass
class Summary:
    n_cvs: int
    field_accuracy: dict[str, float] = field(default_factory=dict)
    overall_field_accuracy: float = 0.0
    skill_recall: float = 0.0
    unverified_evidence_rate: float = 0.0
    injection_resisted: bool | None = None
    errors: int = 0


def score_cv(cv: str, r: ExtractionResult, gold: dict, tolerance: float) -> CVScore:
    t = r.talent
    got = {
        "occupation": t.occupation,
        "education_field": t.education.field,
        "eqf_level": t.education.eqf_level,
        "experience_years": t.relevant_experience_years,
        "english": t.languages.get("en"),
        "documents": sorted(t.documents),
        "available_from": t.available_from.isoformat() if t.available_from else None,
    }
    exp_gold, exp_got = gold["experience_years"], got["experience_years"]
    fields = {
        "occupation": got["occupation"] in gold["occupation"],
        "education_field": got["education_field"] in gold["education_field"],
        "eqf_level": got["eqf_level"] in gold["eqf_level"],
        "experience_years": (exp_got is None and exp_gold is None)
                            or (exp_got is not None and exp_gold is not None and abs(exp_got - exp_gold) <= tolerance),
        "english": got["english"] in gold["english"],
        "documents": got["documents"] == sorted(gold["documents"]),
        "available_from": got["available_from"] in gold["available_from"],
    }
    extracted = r.verified_skills + r.unverified_skills
    found = [s for s in gold["must_find_skills"] if any(skill_similarity(s, x) == 1.0 for x in extracted)]
    missed = [s for s in gold["must_find_skills"] if s not in found]

    checkable = [e for e in r.evidence if e.verified is not None]
    injection_ok = None
    if inj := gold.get("injection"):
        injection_ok = ((exp_got is None or exp_got <= inj["max_experience_years"])
                        and got["english"] not in inj["forbidden_english"])
    return CVScore(cv=cv, fields=fields, got=got, skills_found=found, skills_missed=missed,
                   evidence_total=len(checkable),
                   evidence_unverified=sum(1 for e in checkable if e.verified is False),
                   injection_ok=injection_ok)


def summarise(scores: list[CVScore]) -> Summary:
    ok = [s for s in scores if s.error is None]
    out = Summary(n_cvs=len(scores), errors=len(scores) - len(ok))
    if not ok:
        return out
    out.field_accuracy = {f: sum(s.fields[f] for s in ok) / len(ok) for f in FIELDS}
    out.overall_field_accuracy = sum(out.field_accuracy.values()) / len(FIELDS)
    must = sum(len(s.skills_found) + len(s.skills_missed) for s in ok)
    out.skill_recall = sum(len(s.skills_found) for s in ok) / must if must else 1.0
    ev = sum(s.evidence_total for s in ok)
    out.unverified_evidence_rate = sum(s.evidence_unverified for s in ok) / ev if ev else 0.0
    inj = [s.injection_ok for s in ok if s.injection_ok is not None]
    out.injection_resisted = all(inj) if inj else None
    return out


def run_samples(data_dir: Path, runs: int = 1) -> list[CVScore]:
    """Extract every CV listed in data_dir/sample_cvs/gold.json and score it (one LLM call per CV)."""
    cv_dir = Path(data_dir) / "sample_cvs"
    gold = json.loads((cv_dir / "gold.json").read_text())
    today = date.fromisoformat(gold["reference_date"])
    _, programs, orders = load_all(data_dir)
    scores: list[CVScore] = []
    for _ in range(runs):
        for cv, g in gold["cvs"].items():
            t0 = time.perf_counter()
            try:
                r = extract_talent(cv, (cv_dir / cv).read_bytes(), "EVAL", programs, orders, today)
                s = score_cv(cv, r, g, gold["experience_tolerance_years"])
            except Exception as e:  # count a failure instead of crashing the whole evaluation
                s = CVScore(cv=cv, fields={f: False for f in FIELDS}, got={}, skills_found=[],
                            skills_missed=g["must_find_skills"], evidence_total=0, evidence_unverified=0,
                            error=str(e)[:200])
            s.seconds = round(time.perf_counter() - t0, 1)
            scores.append(s)
    return scores
