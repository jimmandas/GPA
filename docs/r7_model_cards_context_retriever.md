# Context Retriever — Model Card

**Agent:** Context Retriever (Pipeline Step 2 of 4)  
**Model:** Claude API (Anthropic)  
**Model Variant:** claude-3-5-sonnet-20241022  
**Date:** 2026-05-31  
**Phase:** P2 (R7 — Transparency)  

---

## 1. Agent Name & Purpose

**Name:** Context Retriever

**Purpose:** Fetch and synthesize historical patient context (prior imaging, comorbidities, medication history) relevant to the current imaging authorization request.

**Pipeline Stage:** Step 2 of 4 (receives evidence from Step 1)

**Role in system:** The Context Retriever augments extracted findings with historical context. While Evidence Summarizer focuses on the current submission, Context Retriever answers "What do we know about this patient's history that's relevant to this request?" Output is a structured context object used by Policy Mapper and Reasoning Drafter to determine policy match.

---

## 2. Architecture & Design

**Model Family:** Claude (Anthropic)

**Model Variant:** claude-3-5-sonnet-20241022 (frozen; hash-pinned in `config/prompt_hashes.yaml`)

**Prompt Type:** System prompt + structured task description

**Input Interface:** Receives `findings` (from Evidence Summarizer) + `patient_id` + `case_id`

**Output Interface:** JSON schema — structured `context` object with historical findings, comorbidities, prior imaging summary

**Output Schema:**
```json
{
  "prior_imaging": [
    {
      "date": "string (YYYY-MM-DD or 'unknown')",
      "procedure": "string (modality, procedure name)",
      "findings": "string (summary of prior findings)",
      "source": "string (e.g., 'patient_history', 'prior_authorization')"
    }
  ],
  "comorbidities": [
    {
      "condition": "string (ICD-10 or plain text)",
      "source": "string"
    }
  ],
  "prior_approval_rate": "float or null (e.g., 0.85 if ≥5 prior auth records; null if <5)",
  "relevant_contraindications": [
    {
      "contraindication": "string (e.g., 'allergy to IV contrast')",
      "severity": "string (critical | high | moderate)",
      "source": "string"
    }
  ],
  "schema_version": "1.0"
}
```

**Key Design Choices:**
- **Synthetic data simulation:** MVP retriever uses submission + evidence (no real EHR backend); routes to mock context for demo
- **Source discipline:** Each context element cites where it came from (extracted evidence vs. prior auth vs. assumed default)
- **Prior approval rate heuristic:** Rough signal from prior authorization history ("has this patient been approved before?")
- **Contraindication flagging:** Safety-critical information pulled forward
- **No autonomous decision:** Schema forbids `decision` fields (ADR-004)

---

## 3. Input Data & Assumptions

**Input Format:** `findings` (from Evidence Summarizer) + `patient_id` + `case_id`

```json
{
  "findings": {
    "summary": "string",
    "supporting_evidence": [...],
    "uncertainty_flags": [...]
  },
  "patient_id": "string",
  "case_id": "string"
}
```

**Data Contract:**
- `findings` MUST be non-null (populated by Evidence Summarizer)
- `patient_id` MUST be non-empty (required by Admission Gate)
- Agent assumes it can query/simulate historical records (MVP: uses submitted evidence + heuristics)

**Assumptions:**
- **No real EHR backend (MVP):** Context Retriever operates on submitted evidence + simulated history; production will integrate actual EHR
- **Submission contains prior auth history:** Agent relies on `prior_authorizations` list in submission (may be empty/sparse)
- **Patient records are accurate:** Data quality issues in prior records are not agent's job to detect
- **Contraindication data is complete:** Agent assumes major contraindications are documented (may be false if undocumented allergy, etc.)
- **Prior approval patterns are predictive:** Agent uses approval rate heuristic; may not account for policy changes or threshold drifts

**Data Sensitivity:** Receives + outputs PHI (patient history); assumes encrypted/access-controlled EHR connection (MVP: simulated)

---

## 4. Output Behavior & Limitations

**Output Format:** JSON with prior imaging history, comorbidities, prior approval rate, contraindications

**Typical Behavior:**
- Extracts 0–5 prior imaging records (ranges from no history to multiple imaging episodes)
- Lists 0–8 comorbidities (common: diabetes, hypertension, CKD, obesity)
- Calculates prior approval rate if ≥5 prior authorizations exist; null otherwise
- Flags 0–3 contraindications if documented (e.g., "allergy to IV contrast")

**Known Behaviors:**

✅ **Strengths:**
- Standardizes condition names (e.g., "Type 2 diabetes mellitus" → `comorbidities: "diabetes"`)
- Synthesizes multi-record history (e.g., "3 prior CT PE protocols in past 2 years" → `prior_imaging: ["PE protocol CTs"]`)
- Identifies safety-critical contraindications (allergy, renal function, pregnancy)
- Handles sparse history gracefully (empty prior_imaging list vs. hallucinated records)

⚠️ **Known Quirks:**
- **Synthetic data mode (MVP):** Context is generated from submitted data + heuristics; production will integrate real EHR
- **Prior approval rate heuristic:** Uses simple (approved / total) without accounting for changing policies; may be stale
- **Undocumented history:** Agent cannot find contraindications or prior imaging not in submission (e.g., imaging done at outside hospital, not in chart)
- **Date imprecision:** If prior records lack specific dates, agent marks them "unknown" rather than inferring

**Failure Modes:**

| Mode | Detection | Example | Severity |
|---|---|---|---|
| **Missing prior history** | Implicit in completeness; caught by physician review if significant | Outside hospital imaging not in submission; agent has no record of prior PE | Medium (physician may miss; would be caught in follow-up) |
| **Hallucinated contraindication** | Downstream Policy Mapper checks against evidence | Agent flags "allergy to gadolinium" without citation in evidence | Low (Policy Mapper + physician can verify) |
| **Stale approval-rate heuristic** | Not detected by agent; discovered in fairness testing | Prior approval rate = 0.8, but policy threshold just tightened; heuristic misleads | Medium (informational only; physician decides) |
| **Comorbidity name variance** | Not detected; physician must recognize synonyms | Prior record: "CKD Stage 3b"; agent yields "chronic kidney disease" vs. "renal impairment" | Low (human recognizes; informational) |

---

## 5. Fairness & Bias Considerations

**Known Bias Risks:**

| Risk | Source | Impact | Mitigation |
|---|---|---|---|
| **Missing history by institutional access** | Data: Only records in submitted data available | Underinsured / mobile patients with outside records may have incomplete history | Physician review catches critical gaps; logged for appeal |
| **Documentation bias (comorbidity)** | Data: Underdiagnosis of comorbidities in certain populations (e.g., limited healthcare access) | Patients with fewer comorbidities documented may appear "simpler" clinically; confounds disease severity | Physician review accounts for social context; escalation layer for uncertain cases |
| **Prior approval rate bias (proxy for patient compliance/persistance)** | Heuristic: Approval rate may correlate with SES/insurance type | Patients with sparse prior auth history appear "novel" (no signal); may bias downstream policies | Physician sees raw prior_imaging list + approval rate (not automatic); can override heuristic |
| **Contraindication documentation disparities** | Data: Allergy/contraindication documentation completeness varies by demographics | Underdocumented contraindications → missing safety flags → disparate adverse-event risk | Physician review layer; mandatory escalation for contraindication flags |

**Current Mitigations (MVP):**
- Source discipline: Every context element cites where it came from
- Explicit "unknown" for missing dates/sparse records (not hallucinated defaults)
- Mandatory human review: physician sees prior imaging list + approval rate + comorbidities + escalation decision
- Escalation on ambiguous/low-signal cases (catches missed history)
- Full audit trail: context output logged and reviewable

**Deferred to Phase 3 (R4/R5):**
- Fairness testing: measure approval rates + comorbidity profiles by cohort on real patient data
- If disparate-impact detected: analyze documentation patterns by demographics and remediate (e.g., prompt engineering, threshold adjustment)

---

## 6. Performance & Calibration

**Evaluation Metric:** Not directly scored in P1 eval (informational agent)
- Note: Context Retriever outputs inform downstream Policy Mapper, which is scored

**Per-Case Cost (from telemetry, P1 eval):**
- Average: $0.04/case (Claude API usage)
- Range: $0.02–$0.08 (depends on history length)
- Model: claude-3-5-sonnet-20241022

**Latency (P1 eval, 15-case eval run):**
- p50: 1.2 seconds
- p90: 2.1 seconds
- p99: 4.5 seconds

**Stability:**
- **Determinism:** Given frozen model + frozen prompt, outputs are deterministic
- **Completeness:** Always returns complete context object (never crashes or omits fields)
- **Safety:** No contraindications → empty `relevant_contraindications` list (not null)

**Calibration:**
- Conservative extraction (prefers "unknown" over hallucination)
- Prior approval rate only output if ≥5 prior authorizations (statistical threshold to avoid overfitting)

---

## 7. Usage Recommendations

**When to Use:**
- ✅ Any case with prior authorization history (agent adds historical context)
- ✅ Cases where prior imaging is relevant to current request (e.g., follow-up imaging)
- ✅ Cases where comorbidities matter for clinical decision (e.g., renal function for contrast agents)

**When NOT to Use:**
- ❌ De novo cases with no prior history available (agent will return empty lists; still valid)
- ❌ Cases where real-time EHR access is critical (MVP uses submitted data; production will integrate actual EHR)

**Risks if Misused:**
- If context is treated as decision input without validation, hallucinated contraindications may be believed
- If prior approval rate is used as automatic approval signal, policy drift/threshold changes are not accounted for
- If missing history is not acknowledged, incomplete context may bias physician decision

**Responsible Deployment:**
- Physician should note missing outside records (document in decision rationale)
- Prior approval rate is heuristic only; physician should review actual prior records
- Contraindications should be verified against submission evidence
- Monthly audit for missing history patterns by cohort (signals data access disparities)

---

## 8. Known Limitations

- ❌ **MVP: Synthetic context:** No real EHR backend in MVP; production integration required for deployment
- ❌ **Missing outside records:** History limited to submitted data; imaging/records from other hospitals may not be available
- ❌ **Stale approval heuristic:** Does not account for policy threshold changes or clinical guideline updates
- ❌ **Undocumented contraindications:** Cannot find safety information not in chart (e.g., recently discovered allergy not yet documented)

---

## 9. Audit & Transparency

**Output is Logged:**
- Full `context` JSON logged in `pre_state_record` (bilateral logger, hash-chained)
- Submitted as input to Policy Mapper + Reasoning Drafter
- Visible in nurse review UI
- Regulator can query audit log and inspect context for any case

**Reproducibility:**
- Given `findings` + frozen model + frozen prompt, output is deterministic
- Regulator can replay case and inspect context object

**No Autonomous Output:**
- Agent output is informational context, not decision
- No `approval` or `decision` field in output schema

---

## 10. Appendix: References

- **Agent Implementation:** `agents/context_retriever.py`
- **Prompt Hash:** `config/prompt_hashes.yaml`
- **Output Schema:** `schemas/context_retriever_output.json`
- **Bilateral Logger:** `logs/bilateral_logger.py`
- **Policy Mapper:** `agents/policy_mapper.py` (uses context)
- **System Card:** `docs/r7_system_card.md`

---

**End of Context Retriever Model Card**
