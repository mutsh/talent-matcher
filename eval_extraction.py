"""Command line: evaluate CV extraction against hand-labelled data (data/sample_cvs/gold.json).

    python eval_extraction.py            # one pass over the sample CVs (3 Gemini calls)
    python eval_extraction.py --runs 3   # repeat to check consistency

Reads GEMINI_API_KEY from the environment or .streamlit/secrets.toml.
Saves data/sample_cvs/eval_results.json.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import tomllib

from matcher import llm
from matcher.evaluation import FIELDS, run_samples, summarise

ROOT = Path(__file__).parent


def load_local_secrets() -> None:
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        for k, v in tomllib.loads(path.read_text()).items():
            if isinstance(v, str) and not os.getenv(k):
                os.environ[k] = v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    runs = ap.parse_args().runs
    load_local_secrets()
    if not llm.available():
        raise SystemExit("GEMINI_API_KEY not found (environment or .streamlit/secrets.toml).")

    print(f"Model: {llm.describe()} · runs: {runs}\n")
    scores = run_samples(ROOT / "data", runs)
    for s in scores:
        if s.error:
            print(f"✗ {s.cv}: ERROR {s.error}\n")
            continue
        print(f"{s.cv} ({s.seconds}s) fields {s.field_accuracy:.0%}")
        for f, ok in s.fields.items():
            if not ok:
                print(f"    {f}: got {s.got.get(f)!r}")
        if s.skills_missed:
            print(f"    missed skills: {', '.join(s.skills_missed)}")
        if s.injection_ok is not None:
            print(f"    injection resisted: {'yes' if s.injection_ok else 'NO'}")
        print()

    sm = summarise(scores)
    print("SUMMARY")
    for f in FIELDS:
        print(f"  {f:<18} {sm.field_accuracy.get(f, 0):.0%}")
    print(f"  {'overall fields':<18} {sm.overall_field_accuracy:.0%}")
    print(f"  {'skill recall':<18} {sm.skill_recall:.0%}")
    print(f"  {'unverified quotes':<18} {sm.unverified_evidence_rate:.0%} (lower is better)")
    print(f"  {'injection resisted':<18} {sm.injection_resisted}")
    print(f"  {'errors':<18} {sm.errors}")

    out = ROOT / "data" / "sample_cvs" / "eval_results.json"
    out.write_text(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"),
                               "model": llm.describe(), "runs": runs, "summary": sm.__dict__,
                               "per_cv": [s.__dict__ for s in scores]}, indent=2, default=str))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
