# Talent matcher

Shows which talent is eligible for which work-permit or trainee **program** and why, ranks eligible talent for each **employer order**, and explains every suggestion in plain words. A recruiter can add talent from a CV, with Gemini doing the reading and a person reviewing the result.

> Program rules and all data are **illustrative**, not legal thresholds. Use synthetic CVs only.

## Approach
1. **Programs are data, not code.** Each program is a versioned rule set in `data/programs.json`: eligibility rules, required documents, processing time, sectors and occupations.
2. **Eligibility is deterministic, with four outcomes:** eligible, eligible once documents arrive, needs review (data missing), or not eligible. Each outcome names the rule that decided it. No AI is used in this step.
3. **Orders select programs.** Country, sector and occupation decide which programs can serve an order. Document collection plus permit processing time decide who can arrive by the start date.
4. **Ranking is a transparent score.** Every point has a reason, and everyone who is *not* suggested gets a reason too.
5. **AI is used only where text is messy:** CV → structured profile (with evidence quotes and human review), and optional rewording of explanations (guarded against invented facts).

## Run it
```bash
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py        # the app
python -m pytest -q                   # 30 tests, no API key needed
python cli.py --today 2026-10-13      # matching results in the terminal
python eval_extraction.py             # extraction quality vs hand-labelled CVs (needs key)
```
AI features need a free Gemini key from aistudio.google.com. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set `GEMINI_API_KEY`. Without a key, everything except CV extraction and rewording works.

## Project structure
```
app.py                  wires the app together: sidebar, approach panel, four tabs
ui/                     one module per screen, each with render(ctx)
  match_tab.py          pick an order → Run match → ranked, explained suggestions
  add_talent_tab.py     CV → Gemini extraction → review form → talent pool; evaluation button
  eligibility_tab.py    talent × program matrix with the rule trace
  data_tab.py           the rules and data behind every decision
  context.py            Ctx: what every screen needs, passed explicitly
matcher/                all logic; no UI code, so it can sit behind an API unchanged
  models.py             Pydantic schemas: Talent, Program, Rule, Order, results
  eligibility.py        rule engine: talent × program → status + reason per rule
  ranking.py            order → applicable programs → filters → score → sort
  skills.py             skill matching (swap point for ESCO + embeddings)
  explain.py            plain-language explanations + guarded LLM rewording
  extraction.py         CV → evidence-checked profile proposal
  llm.py                the only file that calls Gemini
  evaluation.py         scores extraction against data/sample_cvs/gold.json
data/                   programs, talents, orders, sample CVs and their gold labels
tests/                  rules, ranking, extraction (simulated Gemini), evaluation, UI
deploy/azure/           one-shot Azure Container Apps deploy script
```

## How one talent is matched to one order
1. **Legal:** the talent must be eligible, or eligible once documents arrive, under at least one program that can serve the order. If several programs fit, the one with the earliest start is used.
2. **Employer minimums:** experience and English. If either is unknown, the talent goes to review rather than being rejected.
3. **Relevance:** someone from a different trade who matches under half of the required skills is not suggested, and the reason is shown.
4. **Score (0–100):** required skills 40, experience 15, occupation 10, nice-to-have skills 10, documents 10, timeline 10, English 5.

A candidate who tops several orders is flagged. Allocating people across competing orders is a next step.

## AI guardrails
- **Structured output:** the JSON schema has `null` for "not stated" and controlled vocabularies for occupation, field and documents, so the output plugs straight into the rules.
- **Evidence:** every extracted item carries a quote. Code checks each quote against the document, and unverified skills are unticked.
- **Arithmetic in code:** years of experience come from role dates, with overlapping roles counted once. Gemini does no arithmetic.
- **Human review:** a recruiter confirms or edits every profile before it is matched.
- **Prompt injection:** the CV is treated as data, and scoring is deterministic. See the `injection test` sample.
- **Privacy:** the schema has no fields for age, gender, nationality, religion or photo.
- **Rewording:** a rewrite is rejected if it introduces a number that isn't in the decision trace.

## Responsible use
- Recruitment ranking is high-risk under the EU AI Act, and GDPR Art. 22 applies. A person makes the decision, results record the rule version, and nobody is rejected automatically.
- The evaluation set has 3 synthetic CVs. That demonstrates the method; it is not an accuracy claim.

## Next steps
- Persistence and an API (FastAPI), with eligibility computed once and updated only when something changes.
- Allocation across competing orders.
- Rule drafting from regulation text, with sign-off.
- An evaluation set of real, consented CVs (including Danish and scanned ones).
- SSO and audit logs.

Deployment: see [DEPLOY.md](DEPLOY.md).
