"""Tab 3: every talent against every program, with the rule trace for any cell."""
import pandas as pd
import streamlit as st

from matcher.eligibility import eligibility_matrix
from matcher.explain import explain_eligibility
from matcher.models import Status

from .context import Ctx

ICON = {Status.ELIGIBLE: "✅ Eligible", Status.PENDING_DOCS: "📄 Docs missing",
        Status.UNKNOWN: "❓ Review", Status.NOT_ELIGIBLE: "❌ No"}


def render(ctx: Ctx) -> None:
    mx = eligibility_matrix(ctx.pool, ctx.programs)
    st.dataframe(pd.DataFrame([{"talent": f"{t.id} {t.name}", "occupation": t.occupation or "?",
                                **{p.id: ICON[mx[(t.id, p.id)].status] for p in ctx.programs}} for t in ctx.pool]),
                 hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    t = c1.selectbox("Explain talent", ctx.pool, format_func=lambda x: f"{x.id} {x.name}")
    p = c2.selectbox("for program", ctx.programs, format_func=lambda x: x.name)
    st.text(explain_eligibility(mx[(t.id, p.id)], p))
