"""Typed data model for the three sides of the match: talent, programs, employer orders.

Pydantic validates the input files, so bad data fails loudly at load time
instead of silently producing a wrong match.
"""
from __future__ import annotations

import json
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]


# ---------- Talent side ----------
class Education(BaseModel):
    level_name: str = ""
    eqf_level: int | None = Field(default=None, ge=1, le=8)   # European Qualifications Framework level
    field: str | None = None


class Talent(BaseModel):
    """None means 'not stated'. The rules engine turns that into 'needs review', never a silent no."""
    id: str
    name: str                                   # display only, never used in scoring
    occupation: str | None = None
    education: Education = Education()
    relevant_experience_years: float | None = Field(default=None, ge=0)
    skills: list[str] = []
    languages: dict[str, str] = {}              # e.g. {"en": "B2"}; missing = unknown
    documents: list[str] = []
    available_from: date | None = None
    source: str = "seed"                        # "seed" or "extracted" (added via AI extraction)


# ---------- Program (rules & regulations) side ----------
class Rule(BaseModel):
    id: str
    field: str                                  # dotted path into Talent, e.g. "education.eqf_level"
    op: Literal["in", ">=", "cefr>=", "in_program_occupations"]
    value: Any = None
    text: str                                   # plain-language version of the rule


class Program(BaseModel):
    id: str
    name: str
    country: str
    version: str                                # rules are versioned so every decision is reproducible
    sectors: list[str]
    occupations: list[str]
    processing_weeks: int
    rules: list[Rule]
    required_documents: list[str]


# ---------- Employer side ----------
class Order(BaseModel):
    id: str
    employer: str
    country: str
    sector: str
    occupation: str
    headcount: int
    start_date: date
    required_skills: list[str]
    nice_to_have_skills: list[str] = []
    min_experience_years: float = 0
    min_english: str = "A1"


# ---------- Outputs ----------
class Status(str, Enum):
    ELIGIBLE = "Eligible"
    PENDING_DOCS = "Eligible, documents missing"
    UNKNOWN = "Needs review (data missing)"
    NOT_ELIGIBLE = "Not eligible"


class RuleResult(BaseModel):
    rule_id: str
    passed: bool | None                         # None = could not evaluate (missing data)
    reason: str


class EligibilityResult(BaseModel):
    talent_id: str
    program_id: str
    program_version: str
    status: Status
    rule_results: list[RuleResult]
    missing_documents: list[str]


class ScoreComponent(BaseModel):
    name: str
    points: float
    max_points: float
    reason: str


class Suggestion(BaseModel):
    talent: Talent
    program_id: str
    program_name: str
    eligibility: EligibilityResult
    score: float
    components: list[ScoreComponent]
    earliest_start: date
    on_time: bool
    explanation: str = ""


# ---------- Loading ----------
def load_all(data_dir: str | Path) -> tuple[list[Talent], list[Program], list[Order]]:
    d = Path(data_dir)
    talents = [Talent(**t) for t in json.loads((d / "talents.json").read_text())["talents"]]
    programs = [Program(**p) for p in json.loads((d / "programs.json").read_text())["programs"]]
    orders = [Order(**o) for o in json.loads((d / "orders.json").read_text())["orders"]]
    return talents, programs, orders
