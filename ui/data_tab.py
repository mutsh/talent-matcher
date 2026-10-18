"""Tab 4: the rules and data behind every decision."""
import pandas as pd
import streamlit as st

from .context import Ctx


def render(ctx: Ctx) -> None:
    for p in ctx.programs:
        with st.expander(f"{p.name} · v{p.version} · {p.processing_weeks} weeks processing"):
            st.write("Rules:", [r.text for r in p.rules])
            st.write("Required documents:", p.required_documents)
            st.write("Sectors:", p.sectors, "Occupations:", p.occupations)
    st.dataframe(pd.DataFrame([t.model_dump(mode="json") for t in ctx.pool]), width="stretch")
    st.dataframe(pd.DataFrame([o.model_dump(mode="json") for o in ctx.orders]), width="stretch")
