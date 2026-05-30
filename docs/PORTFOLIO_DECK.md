# GPA — Portfolio Deck for CAIO / AI PM Hiring Manager

**Audience:** CAIO or senior AI PM hiring manager evaluating candidates for governed AI in regulated industries
**Format:** Markdown slide deck (slides separated by `---`). Renders as a deck via Marp, Pandoc, or any markdown-presentation tool.
**Read time:** 5–8 minutes
**Author:** Jim Mandas

---

## Slide 1 — Title

# GPA
## Governed Prior Authorization

**A multi-agent governed AI workflow, built for regulated decision support.**

The portfolio claim is not the product. The claim is **the discipline that produced it.**

Jim Mandas · 2026

---

## Slide 2 — The opening claim

# What this proves

I can ship governed AI for regulated industries — with architectural guarantees, measured outcomes, and honest limits — at the bar a senior AI PM is hired against.

> Most AI portfolios show a working demo.
> This portfolio shows **a working demo that measures itself, names its failures, and produces transferable craft.**

That's the difference between a candidate who built something and a candidate hiring committees can trust with production risk.

---

## Slide 3 — Why this matters now

# The category gap

| What the market is producing | What's missing |
|---|---|
| Vendor "AI-powered PA" wrappers | Audit substrate, determinism, decision-rights enforcement |
| Responsible-AI framework white papers | Working systems with measured outcomes |
| Internal payer experiments | Portable craft, reproducible methodology |

The gap is **shippable governance** — production-grade discipline applied to AI in regulated workflows.

That's the category I built into.

---

## Slide 4 — What I built

# System at a glance

```
┌─────────────────────────────────────────────────────────┐
│  4 Agents (Sequential)                                  │
│  evidence_summarizer → context_retriever                │
│  → policy_mapper → reasoning_drafter                    │
├─────────────────────────────────────────────────────────┤
│  5 Hard Control Gates (Architectural)                   │
│  admission · source_verification · ai_decision_limit    │
│  · denial · confidence                                  │
├─────────────────────────────────────────────────────────┤
│  Bilateral Audit Logger (write-before-emit + fsync)     │
│  Every event hashed. Every action durable.              │
├─────────────────────────────────────────────────────────┤
│  Eval Framework v3 (18 dims × 3 stakeholder buckets)    │
│  Value · Trust · Operational Reliability                │
└─────────────────────────────────────────────────────────┘
```

Multi-agent. Governed. Measured. Auditable.

---

## Slide 5 — The architectural governance move

# AI cannot emit a decision

Not because we instructed it not to.

**Because the JSON schema has no `decision` field.**

```
reasoning_brief.json (the AI's output schema)
  ✓ supporting_evidence: []
  ✓ uncertainty_flags: []
  ✗ decision: <does not exist>
  ✗ recommendation: <does not exist>
  ✗ confidence: <does not exist>
```

The AI-Decision-Limit Gate runs after every agent call and asserts no forbidden field appeared. Across **75 pipeline runs on 15 cases**, this gate held at **1.00 / 0 violations**.

That's enforced governance. Not policy governance. Not aspirational. Structural.

---

## Slide 6 — How the eval is organized

# Three stakeholder buckets

| Bucket | The question it answers | Audience |
|---|---|---|
| **Value / Outcomes** | "Did it matter?" | Hiring manager, design partner |
| **Trust** | "Can we rely on it safely?" | Regulator, compliance, audit |
| **Operational Reliability** | "Can it operate at scale?" | Engineering, SRE, operations |

18 dimensions distributed across the 3 buckets. The Trust bucket nests all 6 RAI evaluation categories.

The bucket framing is **stakeholder-question-first**. Most AI eval frameworks organize around researcher categories. This one organizes around the question the reader is reading the report to answer.

---

## Slide 7 — Live numbers

# Results from this morning's eval

15 cases × 5 reps = **75 pipeline runs**. Sonnet (dev tier). Real SDK telemetry.

| Bucket | Pass rate | Highlight |
|---|---|---|
| **Value** | 3/4 ✓ | Real cost $0.291/case (SDK-measured, not modeled). ROI $+2.73/case. p50 wall 58.4s. |
| **Trust** | 7/8 scored ✓ | Adversarial bypass rate **0%**. Citation correctness **1.00**. Faithfulness 0.97 (cross-vendor judge). |
| **Operational** | 2/3 scored ✓ | p90 latency 77.9s. Reproducibility 0.89. |

Cost is measured from the SDK, not estimated from token counts. **That distinction matters when a CAIO asks "how do you actually know your AI cost?"**

---

## Slide 8 — Honest failures, named

# What's NOT working — and why we say so

Three dims failed. We document each instead of hiding them.

| Failing dim | Root cause | Backlog reference |
|---|---|---|
| `false_escalation_rate` 60% | Sonnet over-escalates judgment-intensive cases; Opus tightens this. | PHASE_3_BACKLOG #17 |
| `clinical_signal_accuracy` 58% | Sonnet variance on schema-strict outputs on hard cases. | Known limit; ship-tier resolves. |
| `pipeline_completion_rate` 59% | Sonnet stability issues on adversarial cases. | Documented; Opus reduces but doesn't eliminate. |

**Why this is a strength, not a weakness:**

A hiring committee reading "15/15 passing" reads luck or deception. A hiring committee reading "8/15 passing with named root causes and documented trigger conditions for resolution" reads **judgment**.

The honest-failure list IS the credibility move.

---

## Slide 9 — Process artifacts extracted

# The portfolio is more than the project

From the build, I extracted **11 transferable craft artifacts** beyond the system itself:

**8 PM-planning templates** (apply to any AI build):
1. Eval version roadmap
2. Eval stakeholder map
3. Milestone definitions (demo / pilot / regulator bars)
4. Operational Contract (numerical thresholds)
5. Failure-mode coverage matrix
6. Customer anchor declaration
7. Project memory loading (cross-session continuity)
8. Python project bootstrap

**2 governance subagents** (project-level reviewers):
- `gpa-eval-critic` — catches eval-framework drift before ship
- `gpa-pre-commit-reviewer` — catches invariant violations before commit

**1 project-memory model** (4-layer loading + CURRENT_TASK.md bridge)

The ratio of *project + craft artifacts* to *project alone* is the strongest single indicator of senior-strategic PM operation.

---

## Slide 10 — Pattern transfer

# Craft generalizes; one project demonstrates portability

The 11 artifacts above are deliberately architecture-agnostic. They apply to:

- Different verticals (regulatory affairs, financial services, clinical research)
- Different retrieval architectures (graph RAG, hybrid, agentic search)
- Different governance regimes (HIPAA, SOC2, FDA-equivalent)

The next project will be a deliberate pattern transfer to a different vertical and a different retrieval architecture — built with the same templates, the same governance discipline, the same measurement framework.

The transfer IS the senior-PM-craft claim. **One project shows a result. The portable craft shows it wasn't an accident.**

---

## Slide 11 — What this means for hiring

# The candidate fit

| What you're hiring for | What this artifact demonstrates |
|---|---|
| Ship AI in production safely | Architectural governance, audit substrate, determinism contract, real cost telemetry |
| Measurement maturity | 18-dim eval framework with bucket grouping, honest failure surfacing, cross-vendor judge, recalibrated thresholds |
| Scope discipline | Documented scope deltas, customer-anchor declaration, Phase 3 backlog with trigger conditions, killed work documented (Cohen's κ removed with rationale) |
| Independent judgment | Killed hyped meta-eval (Cohen's κ); refused 15/15 cherry-pick narrative; named the synthetic-data limit explicitly |
| PM craft transferability | 11 portable artifacts extracted from the build |
| Communication discipline | This deck. SCOPE_BASELINE. EVAL_WRITEUP. LOOM_SCRIPT. CURRENT_TASK.md ritual. |

The next 90 days I'm available to apply this discipline to a real production AI initiative in a regulated industry.

---

## Slide 12 — What I'd build with you

# The forward claim

If you hire me to lead a governed AI initiative in your organization, here's the discipline I bring on day 1:

| Week 1 | Customer anchor + milestone definitions + eval version roadmap + stakeholder map. Not code. |
| Week 2 | Operational Contract + failure-mode coverage matrix + scope doc. Quantitative thresholds. |
| Week 3 | First architectural decisions, ADRs, repo skeleton with 4-layer project loading. |
| Week 4 | First measurable eval results against a defined baseline. |
| Month 3 | Demo-ready governed system with honest measurement, named limits, documented scope cuts. |
| Month 6 | Pilot-ready with SME validation, real production telemetry, dataset expansion. |
| Month 12 | Regulator-ready with multi-rater agreement, field evidence, audit trail. |

Same discipline. Different vertical. Real production stakes.

---

## Slide 13 — Closing

# What I'd want from a first conversation

Not a take-home. Not a coding test. A **45-minute walkthrough of your team's hardest governance question** — what you'd lose sleep over if your AI product hit a regulator audit tomorrow.

I'll bring the GPA artifacts. We'll talk through where the discipline transfers to your context and where it doesn't. By the end of the conversation you'll know whether the craft matches the role.

**Contact:**
- Email: jim.mandas@gmail.com
- Portfolio: [github.com/jimmandas/GPA](https://github.com/jimmandas/GPA)
- Loom walkthrough: [link]
- Full strategic analysis: `docs/EVAL_WRITEUP.md` + this deck's source

---

## Speaker notes — for live delivery

**Pacing:** ~30 seconds per slide for a 6-minute walkthrough; ~60 seconds for a 12-minute walkthrough with deeper Q&A pauses.

**Tone:** Confident, evidence-grounded, willing to name limits. Do NOT oversell — the honesty IS the differentiator.

**Most likely CAIO questions:**

1. *"How does this scale to real production?"* — Phase 3 backlog with trigger conditions documents the path; this is demo-ready, not pilot-ready, and we shouldn't pretend otherwise.

2. *"What's the cost story at scale?"* — $0.29/case dev-tier; ~$0.50–0.80/case ship-tier (Opus); real telemetry not estimated.

3. *"What about clinician validation?"* — Single-rater synthesized ground truth; SME sign-off is named as the highest-leverage next investment in PHASE_3_BACKLOG #24. Honest limit.

4. *"Why governance-first rather than accuracy-first?"* — Accuracy without governance is a deploy you can't audit. In regulated industries, ungoverned accuracy doesn't ship.

5. *"What would you do differently next time?"* — Customer anchor decided week 1 (lost ~24 person-hours to mid-project anchor decision). Milestone bars defined week 1 (most scope churn was actually milestone confusion). Both encoded into Templates 03 and 06 for next project.

**Most likely AI PM hiring-manager questions:**

1. *"What was the hardest decision?"* — Killing Cohen's κ. Most candidates would chase it because the literature does. Naming why it doesn't move OKRs and documenting the trade-off is a judgment signal.

2. *"What's the one thing you'd want to do but didn't?"* — Real SME label sign-off. Documented as #24, named cost (~$1–3k via paid clinical review), named highest-leverage next investment.

3. *"How do you know this is portable?"* — 11 artifacts extracted; next project deliberately uses the templates. The transferability question gets answered by the second project; this artifact creates the conditions for that answer.
