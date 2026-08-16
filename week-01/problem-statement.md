# API Incident Explorer
### From Traffic Signals to an Investigation Shortlist

**Week 1 Project (Path B) · Mastering Agentic AI · The Gen Academy**
**Author:** Arunkumar Palanisamy

---

## Problem Statement

At 2 a.m., an alert fires: error rates are climbing on the API platform. The on-call engineer
has minutes, not hours. The first question is never *"what do the metrics look like?"* — it is
**"what is broken, who is affected, and what do I check first?"**

Modern applications depend on APIs to connect users, services, and backend systems. When error
rates rise or response times suddenly increase, on-call engineers and support teams need to
quickly understand where the problem is concentrated and what they should investigate first.

During the early stages of an incident, engineers work through large volumes of API gateway logs
and correlate multiple signals — timestamps, endpoints, HTTP status codes, response times,
backend services, deployment versions, and API consumers. They are trying to answer a small set
of urgent questions:

- **When** did the degradation begin?
- **Which endpoint** is experiencing the most failures?
- **Which backend service** should be investigated first?
- **Which consumers** are most affected?
- **How has latency changed** compared with normal traffic?

The problem is not simply a lack of monitoring data. Traffic dashboards can show request volume,
errors, and latency, while raw logs provide detailed request-level information. The remaining
investigation gap is turning those separate signals into a focused, evidence-based shortlist of
where an engineer should look next.

**API Incident Explorer** addresses this gap by transforming API gateway request logs into an
interactive investigation view. It combines traffic, error-rate, and p95 latency trends with
filtering and a ranked **Top Suspects** view to help an engineer move from *"something is wrong"*
to *"this is where I should investigate first."*

The application is intentionally an **investigation aid, not an automated root-cause analysis
system**. It does not claim that correlation proves causation. Instead, it surfaces observable
evidence about degraded endpoints, suspect backend services, and affected consumers so that an
engineer can make the next investigation decision more quickly and with better context.

This project comes from 19 years of building and supporting enterprise integration platforms —
API gateways, message brokers, and event-driven systems. I have been the person answering these
questions under pressure, which shaped both the questions the dashboard asks and the deliberate
decision not to overstate what the data can prove.

---

## 30-Second Version (for the video intro)

> When an API platform starts failing, the on-call engineer needs to know what is broken, who is
> affected, and what to check first. Dashboards show charts; logs show detail; neither gives you
> a shortlist. This app turns API gateway logs into an investigation shortlist — the degraded
> endpoint, the suspect backend service, the affected consumer, and a plain-English incident
> brief that an engineer can act on.

---

## One-Line Version (for LinkedIn / the repo README)

> Turning raw API gateway logs into an evidence-based investigation shortlist, so an on-call
> engineer starts from a hypothesis instead of a wall of graphs.
