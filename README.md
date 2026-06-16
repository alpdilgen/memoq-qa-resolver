# memoQ QA Resolver

Universal, AI-assisted resolver for **memoQ embedded QA issues**. Reads a `.mqxliff` whose segments already carry memoQ QA warning codes (`<mq:warnings40>`), resolves what it can with zero error automatically, and routes the rest to a human approval UI — for any language pair and any project.

> **Beta — internal testing.**

## Two parts

- **`qa_engine/`** — a UI-agnostic, provider-agnostic Python engine. Reads the embedded QA codes, routes each issue to a per-code resolver (deterministic / AI / report-only), and produces a `ReviewSession` (auto-applied / pending-approval / report-only). `engine.apply()` writes the chosen fixes back to a corrected, format-preserving, XML-validated `.mqxliff`. No UI imports; the AI client is injected.
- **`streamlit_app.py`** — a standalone Streamlit front-end over the engine: upload → resolve → review/approve/edit → download. The same engine is designed to be embedded into the Anova memoQ AI Translator later.

## Run locally

```bash
pip install -r requirements.txt
# optional, enables the AI resolvers (consistency etc.); without it only the
# deterministic whitespace fixes run and AI-judgment issues are reported.
mkdir -p .streamlit && cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit
streamlit run streamlit_app.py
```

## Run the tests

```bash
python -m pytest
```

## Status

- **Phase 1a — engine core (done):** registry, deterministic whitespace resolver, AI inconsistency resolver, `analyze`/`apply`, injectable `AIClient` (Claude Opus 4.8).
- **Phase 1b — Streamlit UI (in progress).**
- **Phase 2 — more resolvers** (terminology, punctuation, capitalization, number format) + adversarial verification.
- **Phase 3 — Anova memoQ AI Translator integration** (Streamlit screen + memoQ Server SOAP round-trip).

See `docs/superpowers/specs/2026-06-16-memoq-qa-resolver-design.md` for the full design.
