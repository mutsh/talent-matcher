"""Tab 2: upload a CV, extract a profile with Gemini, review it, add it to the pool."""
import json

import pandas as pd
import streamlit as st

from matcher import llm
from matcher.evaluation import run_samples, summarise
from matcher.extraction import DOCUMENT_TYPES, ExtractionResult, extract_talent, vocabularies
from matcher.models import CEFR_ORDER, Education, Talent

from .context import Ctx

MAX_EXTRACTIONS_PER_SESSION = 10   # protects the API key on a public demo
MAX_FILE_MB = 5
NOT_STATED = "(not stated)"


def _pick_document(ctx: Ctx) -> tuple[str | None, bytes | None]:
    if st.radio("Source", ["Sample CV", "Upload a file"], horizontal=True) == "Sample CV":
        samples = sorted((ctx.data_dir / "sample_cvs").glob("*.txt"))
        pick = st.selectbox("Sample", samples, format_func=lambda p: p.stem.replace("_", " "))
        with st.expander("Show sample text"):
            st.text(pick.read_text())
        return pick.name, pick.read_bytes()
    up = st.file_uploader("CV file (PDF, DOCX, TXT, PNG, JPG)", type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"])
    return (up.name, up.getvalue()) if up else (None, None)


def _index(options: list, value) -> int:
    return options.index(value) if value in options else 0


def _review_form(ctx: Ctx, d: ExtractionResult) -> Talent | None:
    """Every extracted value is editable; returns the confirmed Talent when submitted."""
    v = vocabularies(ctx.programs, ctx.orders)
    t = d.talent
    occ_opts, fld_opts = [NOT_STATED] + v["occupations"], [NOT_STATED] + v["fields"]
    eqf_opts, en_opts = [NOT_STATED] + list(range(1, 9)), [NOT_STATED] + CEFR_ORDER
    with st.form("review"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name (display only)", t.name)
        occ = c2.selectbox("Occupation", occ_opts, index=_index(occ_opts, t.occupation))
        avail_known = c3.checkbox("Availability stated", value=t.available_from is not None)
        avail = c3.date_input("Available from", value=t.available_from or ctx.today)

        c1, c2, c3 = st.columns(3)
        level = c1.text_input("Education", t.education.level_name)
        fld = c2.selectbox("Field", fld_opts, index=_index(fld_opts, t.education.field))
        eqf = c3.selectbox("EQF level", eqf_opts, index=_index(eqf_opts, t.education.eqf_level))

        c1, c2 = st.columns(2)
        exp_known = c1.checkbox("Experience known", value=t.relevant_experience_years is not None)
        exp = c1.number_input("Years in trade", 0.0, 50.0, float(t.relevant_experience_years or 0), 0.5)
        c1.caption(f"Computed: {d.experience_detail}")
        en = c2.selectbox("English (CEFR)", en_opts, index=_index(en_opts, t.languages.get("en")))

        skills = st.multiselect("Skills (unticked = not found in the document)",
                                list(dict.fromkeys(d.verified_skills + d.unverified_skills)),
                                default=d.verified_skills, accept_new_options=True)
        docs = st.multiselect("Documents held", DOCUMENT_TYPES, default=t.documents)
        if not st.form_submit_button("Add to talent pool", type="primary"):
            return None
    known = lambda x: None if x == NOT_STATED else x  # noqa: E731
    return Talent(id=t.id, name=name or "Unnamed candidate", occupation=known(occ),
                  education=Education(level_name=level, field=known(fld), eqf_level=known(eqf)),
                  relevant_experience_years=exp if exp_known else None, skills=skills,
                  languages={} if en == NOT_STATED else {"en": en}, documents=docs,
                  available_from=avail if avail_known else None, source="extracted")


def _show_review(ctx: Ctx, d: ExtractionResult) -> None:
    ss = st.session_state
    st.subheader(f"Review: {ss.draft_name}")
    for note in d.notes:
        st.info(note)
    if d.unverified_skills:
        st.warning("Not found in the document, so unticked: " + ", ".join(d.unverified_skills))
    st.dataframe(pd.DataFrame([{"field": r.field, "value": r.value, "evidence (quote)": r.evidence,
                                "found in document": {True: "✅", False: "⚠️ not found", None: "n/a"}[r.verified]}
                               for r in d.evidence]), hide_index=True, width="stretch")
    if new := _review_form(ctx, d):
        ss.added.append(new)
        ss.pop("draft")
        ss.flash = f"Added {new.id} {new.name}. Open **Match an order** and click **Run match**."
        st.rerun()


def _evaluation(ctx: Ctx) -> None:
    ss = st.session_state
    with st.expander("Extraction quality: evaluate against hand-labelled CVs"):
        st.write("Runs the 3 sample CVs through the extractor and compares the result with hand-labelled "
                 "expected values (`data/sample_cvs/gold.json`). Uses 3 of this session's extractions.")
        enough = ss.n_extractions + 3 <= MAX_EXTRACTIONS_PER_SESSION
        if st.button("Run evaluation", disabled=not (llm.available() and enough)):
            ss.n_extractions += 3
            with st.spinner("Evaluating 3 CVs…"):
                scores = run_samples(ctx.data_dir)
            ss.eval = (scores, summarise(scores))
        if ev := ss.get("eval"):
            scores, sm = ev
            c = st.columns(4)
            c[0].metric("Field accuracy", f"{sm.overall_field_accuracy:.0%}")
            c[1].metric("Skill recall", f"{sm.skill_recall:.0%}")
            c[2].metric("Unverified quotes", f"{sm.unverified_evidence_rate:.0%}", help="Lower is better")
            c[3].metric("Injection resisted", {True: "Yes", False: "No", None: "n/a"}[sm.injection_resisted])
            st.dataframe(pd.DataFrame([{"cv": x.cv, **{f: ("✅" if ok else f"❌ {x.got.get(f)!r}")
                                                         for f, ok in x.fields.items()},
                                        "missed skills": ", ".join(x.skills_missed), "error": x.error or ""}
                                       for x in scores]), hide_index=True, width="stretch")


def render(ctx: Ctx) -> None:
    ss = st.session_state
    st.write("Upload a CV. Gemini extracts a structured profile with evidence quotes, code checks the quotes "
             "against the document and computes experience from the dates, then **you review it before it "
             "joins the pool**.")
    if msg := ss.pop("flash", None):
        st.success(msg)
    if not llm.available():
        st.warning("No Gemini key configured. Add `GEMINI_API_KEY` to the app secrets to enable extraction.")
    st.caption("Use synthetic CVs only: free API tiers may use inputs to improve models. "
               f"Extractions left this session: {MAX_EXTRACTIONS_PER_SESSION - ss.n_extractions}.")

    filename, data = _pick_document(ctx)
    can_run = llm.available() and data is not None and ss.n_extractions < MAX_EXTRACTIONS_PER_SESSION
    if st.button("Extract with AI", type="primary", disabled=not can_run):
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            st.error(f"File is larger than {MAX_FILE_MB} MB.")
        else:
            ss.n_extractions += 1
            with st.spinner("Extracting with Gemini…"):
                try:
                    ss.draft = extract_talent(filename, data, f"U{len(ss.added) + 1:02d}",
                                              ctx.programs, ctx.orders, ctx.today)
                    ss.draft_name = filename
                except Exception as e:
                    ss.pop("draft", None)
                    st.error(f"Extraction failed: {e}")

    if d := ss.get("draft"):
        _show_review(ctx, d)
    _evaluation(ctx)

    if ss.added:
        st.subheader("Added this session")
        rows = [t.model_dump(mode="json") for t in ss.added]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        c1.download_button("Download as JSON", json.dumps(rows, indent=2), "added_talents.json", "application/json")
        if c2.button("Clear added talent"):
            ss.added = []
            st.rerun()
