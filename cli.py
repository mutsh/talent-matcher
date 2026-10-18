"""Print the eligibility matrix and ranked suggestions to the terminal.

Usage: python cli.py [--today YYYY-MM-DD]
"""
import argparse
from datetime import date
from pathlib import Path

from matcher.eligibility import eligibility_matrix
from matcher.explain import explain_suggestion
from matcher.models import load_all
from matcher.ranking import rank_for_order

SHORT = {"Eligible": "OK", "Eligible, documents missing": "DOCS",
         "Needs review (data missing)": "REVIEW", "Not eligible": "--"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=date.today().isoformat())
    today = date.fromisoformat(ap.parse_args().today)
    talents, programs, orders = load_all(Path(__file__).parent / "data")

    print(f"Reference date: {today}\n\nELIGIBILITY (talent x program)")
    m = eligibility_matrix(talents, programs)
    print(f"{'':12}" + "".join(f"{p.id:>20}" for p in programs))
    for t in talents:
        print(f"{t.id + ' ' + t.name:12}" + "".join(f"{SHORT[m[(t.id, p.id)].status.value]:>20}" for p in programs))

    for o in orders:
        progs, sugg, excl = rank_for_order(o, talents, programs, today)
        print(f"\n=== {o.id} {o.employer} | needs {o.headcount} x {o.occupation} by {o.start_date} "
              f"| programs: {', '.join(p.id for p in progs) or 'none'}")
        for i, s in enumerate(sugg, 1):
            print("  " + explain_suggestion(s, o, i))
        for x in excl:
            print(f"  [not suggested] {x.talent.id} {x.talent.name}: {x.reason}")


if __name__ == "__main__":
    main()
