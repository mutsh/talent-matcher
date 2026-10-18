"""What every tab needs, loaded once per run and passed around explicitly."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from matcher.models import Order, Program, Talent


@dataclass
class Ctx:
    data_dir: Path
    programs: list[Program]
    orders: list[Order]
    pool: list[Talent]          # seed talent + talent added in this browser session
    today: date                 # reference date for permit timelines
    use_llm: bool               # reword explanations with Gemini

    def program(self, program_id: str) -> Program:
        return next(p for p in self.programs if p.id == program_id)
