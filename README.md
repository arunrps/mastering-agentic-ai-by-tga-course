# Mastering Agentic AI — Weekly Projects

Project work for [Mastering Agentic AI](https://maven.com/aishwarya-srinivasan/mastering-ai-agents)
(The Gen Academy, Aug 2026 cohort) — Aishwarya Srinivasan & Arvind.

## Week 1 — API Incident Explorer
**Theme:** Data Analysis with Vibe Coding · **Path B** (own application)

Turns synthetic API gateway logs into an investigation shortlist: which endpoint is
failing, which backend is the suspect, which consumer is affected, and what to check
next. Framed deliberately as an investigation aid, not root-cause analysis.

- [Problem statement](week-01/problem-statement.md)
- [Full prompt log](week-01/PROMPTS.md) — every prompt sent to the AI coding assistant
- [Screenshots](week-01/screenshots/)

Built with Streamlit, pandas and plotly on 50,000 rows of seeded synthetic log data
with a deliberately injected incident.

## Run locally

    cd week-01
    pip install -r requirements.txt
    streamlit run app.py
