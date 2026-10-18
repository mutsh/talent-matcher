"""Tab 1: pick an employer order, click Run match, read ranked and explained suggestions."""
import pandas as pd
import streamlit as st

from matcher.explain import explain_eligibility, explain_suggestion, polish_with_llm
from matcher.ranking import competing_orders, rank_for_order, top_picks_by_order

from .context import Ctx


@st.cache_data(show_spinner=False, max_entries=500)
def _polished(text: str) -> tuple[str, bool]:
    return polish_with_llm(text)   # cached, so the same explanation is never sent twice


def _run(ctx: Ctx, order) -> dict:
    progs, sugg, excl = rank_for_order(order, ctx.pool, ctx.programs, ctx.today)
    texts = []
    for i, s in enumerate(sugg, 1):
        text = explain_suggestion(s, order, i)
        texts.append(_polished(text) if ctx.use_llm else (text, False))
    picks = top_picks_by_order(ctx.orders, ctx.pool, ctx.programs, ctx.today)
    label = {o.id: f"{o.id} · {o.employer}" for o in ctx.orders}
    others = [[label[oid] for oid in competing_orders(s.talent.id, order.id, picks)] for s in sugg]
    return {"order": order, "progs": progs, "sugg": sugg, "excl": excl, "texts": texts, "others": others}


def _suggestion_card(i, s, text, used, others, ctx: Ctx, polished_run: bool) -> None:
    with st.container(border=True):
        left, right = st.columns([1, 4])
        left.metric(f"#{i} {s.talent.name}", f"{s.score:g}/100")
        left.caption(f"{s.eligibility.status.value} · {'on time' if s.on_time else 'late'}"
                     + (" · added via AI" if s.talent.source == "extracted" else ""))
        right.write(text)
        if others:
            right.warning(f"Also a top pick for {', '.join(others)}. Coordinate before offering.", icon="⚠️")
        if polished_run:
            right.caption("Polished by Gemini" if used else "Template text (rewrite unavailable or rejected)")
        with right.expander("Score breakdown and rule trace"):
            st.dataframe(pd.DataFrame([{"component": c.name, "points": round(c.points, 1),
                                        "max": c.max_points, "why": c.reason} for c in s.components]),
                         hide_index=True, width="stretch")
            st.text(explain_eligibility(s.eligibility, ctx.program(s.program_id)))


def render(ctx: Ctx) -> None:
    ss = st.session_state
    order = st.selectbox("Employer order", ctx.orders, format_func=lambda o: (
        f"{o.id} · {o.employer} · {o.headcount} × {o.occupation} by {o.start_date}"))
    st.write(f"**Required skills:** {', '.join(order.required_skills)} · **Min. experience:** "
             f"{order.min_experience_years:g} y · **Min. English:** {order.min_english}")

    inputs = (order.id, ctx.today.isoformat(), tuple(t.id for t in ctx.pool), ctx.use_llm)
    if st.button("Run match", type="primary"):
        with st.spinner("Matching" + (" and polishing explanations" if ctx.use_llm else "")):
            ss.match = {"inputs": inputs, **_run(ctx, order)}

    m = ss.get("match")
    if not m:
        st.info("Choose an order and click **Run match**.")
        return
    if m["inputs"] != inputs:
        st.warning("Inputs changed since the last run (order, date, talent pool or LLM setting). "
                   "Click **Run match** to refresh.")

    o, progs, sugg, excl = m["order"], m["progs"], m["sugg"], m["excl"]
    st.write(f"Results for **{o.id} · {o.employer}**. Programs that can serve this order: "
             + (", ".join(p.name for p in progs) or "none, so no one can be placed legally"))
    st.subheader(f"Suggested talent ({len(sugg)})")
    for i, (s, (text, used), others) in enumerate(zip(sugg, m["texts"], m["others"]), 1):
        _suggestion_card(i, s, text, used, others, ctx, polished_run=m["inputs"][3])
    if len(sugg) < o.headcount:
        st.warning(f"Only {len(sugg)} suitable candidate(s) for {o.headcount} positions. Sourcing needed.")

    st.subheader(f"Not suggested ({len(excl)})")
    st.dataframe(pd.DataFrame([{"talent": f"{x.talent.id} {x.talent.name}", "reason": x.reason} for x in excl]),
                 hide_index=True, width="stretch")
