# Reasoning Drafter — Model Card

**Agent:** Reasoning Drafter (Pipeline Step 4 of 4)  
**Model:** Claude API (Anthropic)  
**Model Variant:** claude-3-5-sonnet-20241022  
**Date:** 2026-05-31  
**Phase:** P2 (R7 — Transparency)  

---

## 1. Agent Name & Purpose

**Name:** Reasoning Drafter

**Purpose:** Synthesize a human-readable clinical reasoning brief summarizing evidence, policy analysis, and rationale for the nurse and physician to review before making a decision.

**Pipeline Stage:** Step 4 of 4 (final agent before nurse review)

**Role in system:** The Reasoning Drafter is the human-interface agent. Its output is what the nurse actually reads before making an approval/escalation decision. It synthesizes findings (what we know) + policy analysis (what policy says) + context (patient history) into a coherent brief that supports human decision-making. The brief is logged and auditable; it's the artifact that physicians review if they appeal a nurse decision.

---

## 2. Architecture & Design

**Model Family:** Claude (Anthropic)

**Model Variant:** claude-3-5-sonnet-20241022 (frozen; hash-pinned in `config/prompt_hashes.yaml`)

**Prompt Type:** System prompt + few-shot examples + structured task description

**Input Interface:** Receives `findings` + `context` + `policy_map` (synthesizes all three)

**Output Interface:** JSON schema — structured `reasoning_brief` for human consumption

**Output Schema:**
```json
{
  "clinical_summary": "string (2–3 sentences: patient presentation, imaging request, clinical context)",
  "supporting_evidence": [
    {
      "claim": "string (e.g., 'Patient has recurrent PE despite anticoagulation')",
      "source_ref": "string (e.g., 'prior_authorizations[2]')",
      "clinical_significance": "string (why this matters)"
    }
  ],
  "policy_analysis": "string (1–2 sentences: 'Case meets criteria P-1 (prior PE) and P-2 (refractory indication); ambiguous on P-3 (imaging alternatives)')",
  "uncertainty_flags": [
    {
      "flag": "string (e.g., 'indication text ambiguous')",
      "impact": "string (how this affects decision confidence)"
    }
  ],
  "recommendation_rationale": "string (NOT a recommendation; explanation of evidence that supports either approval or escalation)",
  "schema_version": "1.0"
}
```

**Key Design Choices:**
- **Human-first language:** Brief is readable by nurses without medical AI expertise; clear clinical reasoning
- **Not a recommendation:** `recommendation_rationale` explains evidence; does NOT recommend approval/denial (ADR-004)
- **Uncertainty transparency:** Flags that affect confidence are explicit; nurse sees what's ambiguous
- **Policy bridging:** Explicitly connects evidence to policy criteria; nurse understands why criteria met/unmet
- **Source discipline:** Every claim cited; audit trail shows what evidence informed the brief
- **No autonomous decision:** Schema forbids `decision`, `recommendation`, `confidence` fields

---

## 3. Input Data & Assumptions

**Input Format:** `findings` + `context` + `policy_map` (comprehensive pipeline input)

```json
{
  "findings": {
    "summary": "string",
    "supporting_evidence": [...],
    "uncertainty_flags": [...]
  },
  "context": {
    "prior_imaging": [...],
    "comorbidities": [...],
    "prior_approval_rate": "float or null"
  },
  "policy_map": {
    "policy_id": "string",
    "criteria": [...],
    "overall_signal": "meets_criteria | ambiguous | unmet",
    "confidence": "high | medium | low"
  }
}
```

**Data Contract:**
- All three inputs MUST be non-null and well-formed
- `supporting_evidence` and `criteria` MUST have source_ref / passage_id for traceability
- Agent assumes inputs are already validated by earlier agents

**Assumptions:**
- Nurse audience is medically literate (can interpret clinical language)
- Nurse has access to original submission (brief summarizes; does not repeat all details)
- Policy analysis is already complete (Reasoning Drafter does not re-evaluate policy; uses Policy Mapper output)
- Physician will be the final decision-maker on escalated/ambiguous cases

**Data Sensitivity:** Receives PHI (patient history, findings); outputs non-identifying clinical reasoning

---

## 4. Output Behavior & Limitations

**Output Format:** JSON with clinical summary + evidence + policy analysis + uncertainty flags

**Typical Behavior:**
- Clinical summary: 2–3 sentences capturing patient presentation and imaging indication
- Supporting evidence: 3–5 key claims with clinical significance explanations
- Policy analysis: 1–2 sentences connecting evidence to policy criteria
- Uncertainty flags: 0–3 important ambiguities that affect confidence
- Recommendation rationale: 2–3 sentences explaining why case is clear/ambiguous (not a decision)

**Known Behaviors:**

✅ **Strengths:**
- Bridges evidence ↔ policy ↔ decision (nurse sees the connection)
- Flags ambiguities explicitly (nurse knows what's uncertain)
- Uses plain clinical language (nurses can understand without ML background)
- Accurate synthesis of upstream agents' outputs (Policy Mapper + Evidence Summarizer coherence)

⚠️ **Known Quirks:**
- **Summarization bias:** Agent may emphasize certain evidence over others; synthesis is not neutral. Example: Agent may highlight "prior PE" more than "comorbidities" if PE is salient to policy (subjective emphasis).
- **Clinical judgment inference:** Agent sometimes infers clinical significance without explicit source (e.g., "elevated risk" from diabetes + renal impairment without Policy Mapper stating it). Physician may disagree with inference.
- **Linguistic hedging:** Agent uses cautious language ("may suggest", "could indicate") for ambiguous cases; some nurses may interpret as non-committal rather than appropriately uncertain.

**Failure Modes:**

| Mode | Detection | Example | Severity |
|---|---|---|---|
| **Rationalization** | Implicit; caught by physician if case is escalated/appealed | Agent emphasizes supportive evidence, de-emphasizes contradictions (subtle bias) | Medium (physician review catches) |
| **Overstated certainty** | Implicit; visible in confidence field from Policy Mapper | Agent brief sounds clear ("case clearly meets criteria") but Policy Mapper marked confidence=low | Low (policy confidence field alerts physician) |
| **Missed key evidence** | Implicit; caught by nurse if she reads submission directly | Agent brief omits rare but clinically important finding (e.g., allergy notation) | Medium (nurse catches if diligent) |
| **Policy misalignment** | Detected if physician reviews policy + brief separately | Brief says "meets criteria" but Policy Mapper said "ambiguous" (would indicate Logic error) | Low (audit trail shows both) |

---

## 5. Fairness & Bias Considerations

**Known Bias Risks:**

| Risk | Source | Impact | Mitigation |
|---|---|---|---|
| **Summarization emphasis bias** | Agent design: Model selects which evidence to emphasize; may reflect training data biases | Agent brief may over-emphasize findings stereotypically associated with certain demographics; under-emphasize protective factors | Nurse + physician review; transparent evidence list; escalation on uncertain cases |
| **Clinical significance inference bias** | Model behavior: Clinical significance attributed to findings may reflect training data (e.g., "obesity + diabetes" more significant in majority cohorts) | Non-majority populations' clinical presentations may be under-valued or over-valued in brief | Transparent uncertainty flags; physician review layer catches misalignment |
| **Linguistic tone bias** | Prompt design: Language style may be more persuasive for certain presentations | Ambiguous case described cautiously vs. clearly, depending on framing; may bias nurse decision | Policy Mapper confidence field provides objective signal; nurse should use it |
| **Documentation-based synthesis** | Input data: Brief synthesizes findings from submitted evidence; if documentation is sparse/biased, brief inherits bias | Cases with sparse documentation yield sparse briefs; may appear less complex clinically | Transparent evidence references; nurse can see completeness; escalation on incomplete cases |

**Current Mitigations (MVP):**
- Transparent evidence list: nurse sees all supporting evidence with source references
- Explicit uncertainty flags: ambiguities are named and explained
- Policy confidence field: objective signal from Policy Mapper about criterion certainty
- Mandatory human review: nurse reads brief + evaluates independently
- Escalation on ambiguous cases (physician final authority)
- Full audit trail: brief logged with all inputs for retrospective review

**Deferred to Phase 3 (R4/R5):**
- Fairness testing: analyze brief emphasis/tone patterns by cohort on pilot data
- If disparate-emphasis detected: adjust prompt engineering, evidence weighting, or physician guidance
- Model card update with empirical findings

---

## 6. Performance & Calibration

**Evaluation Metric:** `rationale_faithfulness` (eval/dimensions.py)
- Measures: % of brief claims that have supporting evidence citations
- Threshold: ≥80% for pass
- Interpretation: "Are the claims in the brief grounded in evidence?"

**Per-Case Cost (from telemetry, P1 eval):**
- Average: $0.09/case (Claude API usage; largest agent due to synthesis complexity)
- Range: $0.05–$0.15 (depends on brief length)
- Model: claude-3-5-sonnet-20241022

**Latency (P1 eval, 15-case eval run):**
- p50: 3.2 seconds
- p90: 6.1 seconds
- p99: 11.3 seconds

**Stability:**
- **Determinism:** Given frozen model + frozen prompt, outputs are deterministic
- **Completeness:** Always returns complete brief (never crashes or omits required fields)
- **Consistency:** Clinical reasoning is coherent across claims (no internal contradictions observed in P1 eval)

**Calibration:**
- Eval shows agent brief is concise (2–4 pages) and readable by nurse audience
- Faithfulness: 90% of brief claims have valid source citations (P1 eval)

---

## 7. Usage Recommendations

**When to Use:**
- ✅ Any case reaching this stage (Reasoning Drafter is mandatory step 4)
- ✅ Cases where nurse needs clear, synthesized reasoning (brief is primary decision support)
- ✅ Cases where audit trail must include human-readable rationale (brief is logged and auditable)

**When NOT to Use:**
- ❌ Cases where structured data analysis only is needed (use Policy Mapper alone)
- ❌ Cases where nurse has already decided (brief is still generated; not essential if decision made independently)

**Risks if Misused:**
- If brief is treated as a recommendation (violates ADR-004), nurse loses independence and AI gains decision authority
- If uncertainty flags are ignored, nurse underestimates case complexity
- If evidence citations are not verified, nurse may accept unsourced claims

**Responsible Deployment:**
- Nurse should read the full evidence list + policy_map, not just the brief
- Nurse should note any evidence the brief omits that seems important to her
- Escalation decision should account for uncertainty flags, not ignore them
- Monthly audit for brief tone/emphasis patterns by case type (signals summarization bias)

---

## 8. Known Limitations

- ❌ **Not a recommendation:** Brief explains evidence; does NOT recommend approval/denial (enforced at schema layer)
- ❌ **Summarization is selective:** Brief highlights key evidence; nurse should review full evidence list for completeness
- ❌ **Clinical judgment inferred:** Agent infers clinical significance; physician may disagree with inference
- ❌ **Ambiguity not auto-resolved:** Brief highlights ambiguous findings; nurse/physician must interpret

---

## 9. Audit & Transparency

**Output is Logged:**
- Full `reasoning_brief` JSON logged in `pre_state_record` (bilateral logger, hash-chained)
- Returned to nurse (primary decision-support artifact)
- Visible in physician escalation review (physicians read briefs when reviewing escalations)
- Regulator can query audit log and inspect brief for any case

**Reproducibility:**
- Given `findings` + `context` + `policy_map` + frozen model + frozen prompt, output is deterministic
- Regulator can replay case and verify brief matches logged output

**No Autonomous Output:**
- Agent output is reasoning, not decision
- No `decision` or `approval` field in output schema
- `recommendation_rationale` explains evidence; does NOT recommend action
- Nurse decision-making is documented separately in nurse_action_record

**Auditability:**
- Brief source citations trace back to Evidence Summarizer + Context Retriever
- Policy connections trace back to Policy Mapper
- Nurse can verify brief accuracy by checking source evidence
- Physician appeals can reference brief as record of information provided to nurse

---

## 10. Appendix: References

- **Agent Implementation:** `agents/reasoning_drafter.py`
- **Prompt Hash:** `config/prompt_hashes.yaml`
- **Output Schema:** `schemas/reasoning_drafter_output.json`
- **Eval Dimension:** `eval/dimensions.py` → `score_rationale_faithfulness()`
- **Bilateral Logger:** `logs/bilateral_logger.py`
- **Nurse Review Endpoint:** `api/main.py` → `/cases/{case_id}/determine` (returns reasoning_brief)
- **System Card:** `docs/r7_system_card.md`

---

**End of Reasoning Drafter Model Card**
