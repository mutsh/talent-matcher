"""Talent matcher. Run with: python -m streamlit run app.py

This file only wires things together. Logic lives in matcher/ (no UI code), screens in ui/.
"""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from matcher import llm
from matcher.models import load_all
from matcher.ranking import WEIGHTS
from ui import add_talent_tab, data_tab, eligibility_tab, match_tab
from ui.context import Ctx

DATA_DIR = Path(__file__).parent / "data"

APPROACH = """
1. **Programs are data, not code.** Each program is a versioned rule set (eligibility rules, documents,
   processing time). AI can draft rules from regulation text; a person signs them off.
2. **Eligibility is deterministic, with four outcomes:** eligible · eligible once documents arrive ·
   needs review (data missing) · not eligible, each with the rule that decided it. No AI in this step.
3. **Orders select programs.** Country, sector and occupation decide which programs can serve an order;
   document collection + permit processing time decide whether someone can arrive by the start date.
4. **Ranking is a transparent score** (skills, occupation, experience, English, documents, timeline);
   every point has a reason, and everyone *not* suggested gets a reason too.
5. **AI where text is messy:** reading CVs into a structured profile (with evidence quotes and a human
   review) and optionally rewording explanations, guarded against invented facts.
"""


def load_secrets() -> None:
    """Streamlit secrets (hosted, or .streamlit/secrets.toml locally) -> environment, read by matcher.llm."""
    for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TEXT_MODEL"):
        try:
            if not os.getenv(key) and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
        except Exception:      # no secrets file at all: fine, AI features stay off
            return


st.set_page_config(page_title="Talent matcher", layout="wide")
load_secrets()

seed_talents, programs, orders = load_all(DATA_DIR)
ss = st.session_state
ss.setdefault("added", [])            # talent added via extraction, this browser session only
ss.setdefault("n_extractions", 0)

with st.sidebar:
    st.header("Settings")
    today = st.date_input("Reference date", value=date(2026, 10, 13),
                          help="Used to compute permit processing and earliest start dates.")
    use_llm = st.toggle("Polish explanations with Gemini", value=False, disabled=not llm.available(),
                        help="Rewords each explanation. Rewrites that add numbers are rejected.")
    st.caption(f"LLM: {llm.describe()}")
    st.caption(f"Talent pool: {len(seed_talents)} seed + {len(ss.added)} added")
    st.caption("Scoring weights (sum 100)")
    st.dataframe(pd.DataFrame(WEIGHTS.items(), columns=["component", "points"]), hide_index=True)
    st.caption("All rules and data are illustrative, not legal thresholds. Use synthetic CVs only.")

ctx = Ctx(data_dir=DATA_DIR, programs=programs, orders=orders,
          pool=seed_talents + ss.added, today=today, use_llm=use_llm)

st.title("Talent × program × employer matching")
with st.expander("Approach: how this works"):
    st.markdown(APPROACH)

tabs = st.tabs(["Match an order", "Add talent (AI extraction)", "Eligibility matrix", "Rules and data"])
for tab, screen in zip(tabs, (match_tab, add_talent_tab, eligibility_tab, data_tab)):
    with tab:
        screen.render(ctx)
