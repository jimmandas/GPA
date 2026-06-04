# R7 — Model/System Cards (Transparency Artifacts)

**Phase:** P2 · **Status:** 🟡 In progress · **Owner:** Jim · **Started:** 2026-05-31

---

## Purpose

Transparency cards enable regulated buyers and their counsel to answer due-diligence questions about how GPA works, its limitations, and its oversight surface — **without a meeting**. NIST/Google established pattern (reference: NIST AI RMF, Google Model Cards for Model Reporting).

**Outcome:** O2 (Demonstrated Trust). Pairs with R10 (risk-acceptance doc).

---

## Scope

Two artifacts:

1. **Model Cards** (per-agent) — document each of the 4 pipeline agents:
   - `evidence_summarizer`
   - `context_retriever`
   - `policy_mapper`
   - `reasoning_drafter`

2. **System Card** (end-to-end pipeline) — document GPA as a whole:
   - Architecture, data flows, decision points
   - Failure modes and mitigations
   - Governance and oversight instrumentation

---

## Definition of Done (Acceptance Criteria)

### Model Cards (each agent)

**Format:** Markdown, ~2–3 pages per agent. Structure:

1. **Agent Name & Purpose**
   - Name: (e.g., "Evidence Summarizer")
   - Purpose: One-sentence role in the pipeline (e.g., "Extracts and organizes clinical evidence from imaging requests and prior history")
   - Pipeline Stage: (e.g., "Step 1 of 4")

2. **Architecture & Design**
   - Model family: (e.g., "Claude API (Anthropic)")
   - Model variant: (e.g., "claude-3-5-sonnet-20241022")
   - Prompt type: (e.g., "System prompt + structured task description")
   - Output format: (e.g., "JSON schema with findings array")
   - Key design choices: (e.g., "Chain-of-thought reasoning; no autonomous decision output; output schema enforces schema_version")

3. **Input Data & Assumptions**
   - Input format: What this agent accepts (e.g., `submission` dict with imaging request, prior auth history)
   - Data contract: Required fields (list)
   - Assumptions: (e.g., "Submission data is well-formed JSON; OCR'd documents may have ~2% character error rate")

4. **Output Behavior & Limitations**
   - Output format: What this agent produces (e.g., JSON with structured findings)
   - Known behaviors:
     - ✅ Handles ambiguous clinical language (e.g., "possible pneumonia" classified as finding, flag noted)
     - ⚠️ May miss implied evidence (e.g., if imaging request says "follow-up PE protocol" but doesn't name PE, may not infer)
     - ⚠️ Occasionally over-extracts from boilerplate (e.g., "per protocol, check X" flagged as a finding)
   - Failure modes:
     - Silent omission: Evidence exists in submission but agent does not extract (rare; not detected at agent layer)
     - Over-extraction: Non-evidence text flagged as evidence (caught by downstream gates)

5. **Fairness & Bias Considerations**
   - Known bias risks:
     - Language bias: Agent trained on English medical text; non-standard terminology (regional, linguistic variant) may be underrepresented
     - Documentation bias: Cases with more detailed imaging notes yield more extracted evidence (confounds clinical complexity)
   - Mitigations:
     - Evidence is downstream-gated (source_verification gate checks if citations are valid)
     - Denial gate requires physician review (human catch-all)
   - Open questions: (e.g., "Does the agent extract evidence differentially across race proxies in imaging workflows? See R4/R5 — deferred pending fairness testing")

6. **Performance & Calibration**
   - Evaluation: How this agent's output is evaluated (e.g., "Eval dim: source_citation_accuracy measures valid citations per finding")
   - Per-case cost: (from telemetry, e.g., "$0.02/case for this agent in live eval")
   - Latency: (e.g., p50: 2.1s, p90: 4.3s)
   - Stability: (e.g., "Deterministic given frozen model + prompt hash; reproducible across runs")

7. **Usage Recommendations**
   - When to use: (e.g., "Any imaging authorization submission with structured imaging request + prior history")
   - When NOT to use: (e.g., "Not suitable for free-text-only submissions (no structured metadata)")
   - Risks if misused: (e.g., "If used without downstream gates, extracted evidence may include non-findings")

---

### System Card (end-to-end pipeline)

**Format:** Markdown, ~3–4 pages. Structure:

1. **System Name & Purpose**
   - Name: "GPA v4 — Governed Prior Authorization Pipeline"
   - Purpose: Summarize in one sentence, buyer-facing (e.g., "An AI-assisted medical prior authorization (PA) pipeline with human oversight, audit trail, and fairness governance")

2. **Components & Data Flow**
   - Diagram (ASCII or link to visual): Shows 4 agents, 5 gates, bilateral logger, physician queue
   - Component list:
     - **Agents:** Evidence Summarizer, Context Retriever, Policy Mapper, Reasoning Drafter
     - **Gates:** Admission, Source Verification, AI Decision Limit, Confidence, Denial
     - **Infrastructure:** Bilateral audit logger (hash-chained, tamper-detectable), Physician Queue (HITL escalation)
   - Data flow: (e.g., submission → agents 1–4 → gates 1–5 → logger write → nurse review → nurse decision + escalation → physician queue)

3. **Governance & Oversight**
   - Automated decision limit: "AI agents output reasoning brief, never a decision. Schema enforces this (ADR-004)."
   - Human-in-the-loop (HITL) gates:
     - Nurse review: All cases before any determination
     - Physician escalation: Cases flagged by confidence gate or source_verification gate
     - Physician denial: Cases where nurse chooses deny (route mode only; MVP blocks all denials, physician decides)
   - Audit trail: "Every step logged to bilateral logger (A1). Hash-chain detects tampering. Physician actions flow into same log (A2)."
   - Denial gate modes:
     - MVP (block): All denials blocked; escalated to physician
     - Route (production): Denials routed to physician for binding decision
   - Risk acceptance: "R10 signed by CAIO. Non-deploy posture: system is blocked from real-patient PHI until R4/R5 (demographic fairness) pass acceptance bar."

4. **Failure Modes & Mitigations**
   - **Agent hallucination / over-extracts evidence:**
     - Detection: Source verification gate checks all citations
     - Mitigation: Invalid citations trigger escalation; nurse/physician review
   - **Silent audit-log failure:**
     - Detection: Impossible (hash-chain verifies log integrity retrospectively)
     - Mitigation: Fail-closed (A3): any logger failure halts the pipeline
   - **HITL gate bypass (AI outputs decision):**
     - Detection: AI Decision Limit gate (schema validation)
     - Mitigation: Schema forbids decision/recommendation/confidence fields (ADR-004)
   - **Nurse / physician error in escalation:**
     - Detection: Logged to audit trail
     - Mitigation: All escalations reviewed by physician (final human veto)
   - **Fairness gap (system treats cohorts unequally):**
     - Detection: R4/R5 fairness testing (deferred Phase 3)
     - Mitigation: R10 non-deploy posture (no real-patient use until fairness passes bar)

5. **Fairness & Bias Governance**
   - Known risks (per R10):
     - Documentation bias: More detailed imaging notes → more evidence extracted (confounds clinical complexity)
     - Language bias: Evidence extraction trained on English; non-standard terminology may be underrepresented
     - Cohort fairness: Unknown whether approval rates, escalation rates, or override rates differ across demographics
   - Mitigations deployed (MVP):
     - Mandatory human review (nurse + escalation physician)
     - Transparent audit trail (regulator can inspect any case)
     - Hash-chained log (tamper-evident)
   - Deferred to Phase 3 (R4/R5):
     - Prospective fairness eval: Run cohort analysis on pilot data
     - Disparate-impact testing: Measure approval-rate deltas across cohorts; remediate or govern
   - Governance: R10 signed; non-deploy until R4/R5 pass acceptance bar (CAIO veto)

6. **Transparency & Accountability**
   - Audit trail: "Every decision logged to bilateral logger. Regulator can run `python verify_audit_log.py case_id` to detect tampering."
   - Reproducibility: "Given frozen model + prompt hash, outputs are deterministic. Regulator can replay case and inspect agent reasoning_brief."
   - Physician queue: "All escalations and physician actions recorded and audited. No off-log decisions."
   - Non-autonomous decision: "Schema enforces zero autonomous denials. Every denial reviewed by physician (route mode) or escalation pipeline (MVP)."

7. **Known Limitations**
   - Not suitable for real-patient PHI (non-deploy posture per R10 until R4/R5 land)
   - Fairness across cohorts unvalidated (demographic fairness testing deferred to Phase 3)
   - Performance on atypical presentations underexplored (eval dataset: 15 synthetic cases; pilot will expand)
   - Appeals flow not yet instrumented (R8 deferred; placeholder escalation-to-physician)

8. **Usage Context**
   - Regulatory standing: "Designed for regulated-tenant deployment (e.g., hospitals, insurance reviewers). Audit trail supports compliance with FDA/state medical board oversight requirements."
   - Buyer diligence: "This card + R10 (risk-acceptance) + eval report (eval/results/) provide transparency for buyer counsel review."
   - Buyer next steps: "Run fairness eval on your patient cohort. If R4/R5-like testing shows acceptable disparate impact, R10 posture can lift."

---

## Acceptance Criteria (Validation)

- ✅ All 4 model cards drafted (1 per agent)
- ✅ System card drafted
- ✅ Each card addresses Fairness & Bias section explicitly (names known risks + mitigations)
- ✅ Limitations section is honest and specific (not generic)
- ✅ No claims made that aren't grounded in code/eval/R10 (no "auditable" without A1; no "fair" without R4/R5)
- ✅ Cards are readable by non-ML audience (buyer counsel, regulator)
- ✅ Cards link to or reference supporting artifacts (eval report, R10, verify_audit_log.py)

---

## Files

- `docs/r7_model_cards_evidence_summarizer.md` — Agent 1
- `docs/r7_model_cards_context_retriever.md` — Agent 2
- `docs/r7_model_cards_policy_mapper.md` — Agent 3
- `docs/r7_model_cards_reasoning_drafter.md` — Agent 4
- `docs/r7_system_card.md` — End-to-end GPA

---

## References

- **NIST AI RMF:** https://airc.nist.gov/AI_RMF_1.0/
- **Google Model Cards:** https://modelcards.withgoogle.com/
- **R10 (Risk-Acceptance):** `~/claude/projects/My AI Team/Owner's Inbox/gpa-risk-acceptance-2026-05-31/`
- **Eval Report:** `eval/results/eval_report_20260529_205655.md` (per-case cost, dimensions, honest failures)
- **Bilateral Logger:** `logs/bilateral_logger.py` (audit trail)
- **Verify Tool:** `verify_audit_log.py` (tamper-evidence)
