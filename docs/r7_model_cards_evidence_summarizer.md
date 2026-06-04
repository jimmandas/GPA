# Evidence Summarizer — Model Card

**Agent:** Evidence Summarizer (Pipeline Step 1 of 4)  
**Model:** Claude API (Anthropic)  
**Model Variant:** claude-3-5-sonnet-20241022  
**Date:** 2026-05-31  
**Phase:** P2 (R7 — Transparency)  

---

## 1. Agent Name & Purpose

**Name:** Evidence Summarizer

**Purpose:** Extract and organize clinical evidence from imaging requests, prior authorization history, and clinical context to support downstream policy mapping and physician decision-making.

**Pipeline Stage:** Step 1 of 4 (entry point after admission gate)

**Role in system:** The Evidence Summarizer is the first data processor. It transforms unstructured/semi-structured clinical information (imaging indication, prior imaging, comorbidities) into a structured findings list, each finding tagged with a source reference. Downstream agents (Context Retriever, Policy Mapper, Reasoning Drafter) build upon this extraction.

---

## 2. Architecture & Design

**Model Family:** Claude (Anthropic)

**Model Variant:** claude-3-5-sonnet-20241022 (frozen; hash-pinned in `config/prompt_hashes.yaml`)

**Prompt Type:** System prompt + structured task description

**Input Interface:** Receives `submission` dict (imaging request, prior history, patient context)

**Output Interface:** JSON schema — structured `findings` array with source references

**Output Schema:**
```json
{
  "summary": "string (one-sentence clinical overview)",
  "supporting_evidence": [
    {
      "claim": "string (e.g., 'Patient has history of recurrent PE')",
      "source_ref": "string (e.g., 'prior_authorizations[2].reason')",
      "source_type": "string (e.g., 'prior_auth', 'imaging_request', 'clinical_history')"
    }
  ],
  "uncertainty_flags": [
    {
      "flag": "string (e.g., 'indication text ambiguous')",
      "source_ref": "string"
    }
  ],
  "schema_version": "1.0"
}
```

**Key Design Choices:**
- **Source reference discipline:** Every `claim` must cite a source; downstream Source Verification Gate validates these citations
- **Uncertainty flagging:** Agent flags ambiguous language (e.g., "possible", "rule out") rather than suppressing it; physician sees the nuance
- **No autonomous decision:** Schema forbids `decision`, `recommendation`, `confidence` fields (ADR-004); enforced at output validation layer
- **Chain-of-thought:** Prompt encourages reasoning steps visible in reasoning_brief; aids human review
- **Deterministic output:** Given frozen model + prompt hash, outputs are deterministic (reproducible)

---

## 3. Input Data & Assumptions

**Input Format:** `submission` dict (JSON)

```json
{
  "case_id": "string (UUID)",
  "patient": {
    "patient_id": "string",
    "age": "integer",
    "conditions": ["string"]
  },
  "imaging_request": {
    "procedure_code": "string (CPT/HCPCS)",
    "indication": "string (clinical reason, free text or structured)",
    "modality": "string (CT, MRI, PET, X-ray, etc.)"
  },
  "prior_authorizations": [
    {
      "date": "string (YYYY-MM-DD)",
      "procedure": "string",
      "reason": "string (approval reason or denial reason)"
    }
  ],
  "clinical_history": "string (free text: comorbidities, medications, relevant history)"
}
```

**Data Contract:**
- `case_id` MUST be present and non-empty
- `imaging_request.indication` MUST be present (may be ambiguous; agent flags if so)
- `clinical_history` MAY be empty or sparse
- `prior_authorizations` MAY be empty list (no prior history)

**Assumptions:**
- Submission data is well-formed JSON (validation is Admission Gate's job)
- Clinical text is English (model trained on English medical text)
- OCR'd documents may contain ~2% character error rate (agent expected to work around common OCR mistakes)
- Prior authorization reasons are human-written and may use non-standard terminology
- Patient age/conditions are reasonably accurate (data quality not agent's job)

**Data Sensitivity:** Receives PHI (patient ID, medical history); outputs non-identifying JSON findings

---

## 4. Output Behavior & Limitations

**Output Format:** JSON with structured findings array + uncertainty flags

**Typical Behavior:**
- Extracts 2–6 findings per case (ranges from single-finding cases to multi-issue cases)
- Flags ambiguous language (e.g., "possible", "r/o") in uncertainty_flags
- Cites specific source document/field for each finding
- Produces summary line suitable for human scanning

**Known Behaviors:**

✅ **Strengths:**
- Handles standard clinical abbreviations (PE, DVT, MI, etc.)
- Disambiguates implicit evidence (e.g., if indication says "r/o PE protocol" and prior imaging shows "PE ruled out", agent infers recent PE history)
- Flags contradictions (e.g., "no history of PE" contradicts indication "PE protocol imaging")
- Structures boilerplate separately (e.g., "per standard protocol, assess..." flagged as boilerplate, not clinical evidence)

⚠️ **Known Quirks:**
- **Over-extraction from boilerplate:** Standard phrase "per protocol, check for X" may be flagged as finding rather than process note. Example: imaging report boilerplate "compare to prior imaging to detect new findings" might yield finding "needs comparison to prior" (low severity; caught by Source Verification Gate)
- **Implicit evidence miss:** If prior indication says "follow-up CT post-PE anticoagulation" without naming PE, agent may not infer "prior PE" (depends on prompt context). Example: case with vague "interval follow-up imaging" may miss that prior case was PE.
- **Linguistic variance:** Regional or uncommon clinical shorthand (e.g., non-standard abbreviations used only at specific institutions) may not be recognized. Example: "Abd pain + SOB → r/o pulm + abd" uses non-standard punctuation; agent may over-fragment this into separate claims.

**Failure Modes:**

| Mode | Detection | Example | Severity |
|---|---|---|---|
| **Silent omission** | Not detected by agent; caught by human review + physician escalation | Evidence exists in submission but agent does not extract | Medium (depends on physician attention; logged for appeal) |
| **Over-extraction** | Source Verification Gate checks citations | Non-finding boilerplate flagged as evidence; gate invalidates citation | Low (gate catches) |
| **Conflicting claims** | Logged as separate findings; human must resolve | Agent extracts both "no PE history" and "PE indication" without reconciliation | Medium (human must reconcile) |
| **Hallucination** | Source Verification Gate checks citations | Agent invents a claim with invalid source_ref | Low (gate rejects) |

---

## 5. Fairness & Bias Considerations

**Known Bias Risks:**

| Risk | Source | Impact | Mitigation |
|---|---|---|---|
| **Language bias** | Training data: English medical text; non-English or regional variants underrepresented | Agent may miss terminology common in non-English-speaking regions or linguistic minorities | Human review catches misses; physician final authority |
| **Documentation bias** | Data-generation: More detailed imaging notes yield more extracted evidence | Cases with verbose documentation appear "stronger" clinically; confounds disease severity | Logged as evidence count; eval dimension flags completion_rate; physician reviews all details |
| **Socioeconomic proxy via documentation** | Indirect: Patients with fewer resources may have less detailed prior documentation | Sparse documentation → fewer extracted findings → may bias downstream approval → approval-rate disparities across SES | Transparent escalation; physician review layer; R4/R5 fairness testing |
| **Implicit clinical assumption bias** | Model training: Certain demographic presentations are rarer in training data | Agent may extract less evidence for uncommon presentations (e.g., atypical symptom clusters) | Physician escalation + human review; flagged as uncertainty |

**Current Mitigations (MVP):**
- Source Verification Gate validates all citations (catches hallucinations)
- Mandatory human review: nurse reviews all findings before any determination
- Physician escalation on ambiguous cases (uncertainty flags) or low-signal cases
- Full audit trail: all extractions logged and reviewable

**Deferred to Phase 3 (R4/R5):**
- Prospective fairness testing: measure approval rates by cohort after fairness testing on pilot data
- If disparate-impact detected in evidence extraction: analyze documentation bias by cohort and remediate (e.g., adjust thresholds, prompt engineering)
- Model card update with empirical fairness findings

---

## 6. Performance & Calibration

**Evaluation Metric:** `source_citation_accuracy` (eval/dimensions.py)
- Measures: % of extracted findings with valid source citations
- Threshold: ≥80% for pass
- Interpretation: "Agent extracted claims; did it cite valid sources?"

**Per-Case Cost (from telemetry, P1 eval):**
- Average: $0.08/case (Claude API usage)
- Range: $0.05–$0.12 (depends on submission size)
- Model: claude-3-5-sonnet-20241022

**Latency (P1 eval, 15-case eval run):**
- p50: 2.1 seconds
- p90: 4.3 seconds
- p99: 8.7 seconds

**Stability:**
- **Determinism:** Given frozen model + frozen prompt hash, outputs are deterministic (can replay case and verify)
- **Reproducibility:** 100% reproducible across runs (no random sampling in prompt)
- **Variance:** Non-zero token variance in Claude API; outputs are semantically stable but may vary in phrasing

**Calibration:**
- Eval shows agent extraction is conservative (few false positives, some false negatives in detail)
- Source Verification Gate expects ~75–90% citation accuracy (observed in P1 eval)
- Completion_rate metric flags 0-finding cases; these score N/A on citation_accuracy (no inflation)

---

## 7. Usage Recommendations

**When to Use:**
- ✅ Any structured imaging authorization submission with imaging request indication + patient context
- ✅ Cases with prior authorization history (agent uses history for context)
- ✅ Cases where clinical reasoning must be transparent (agent outputs structured reasoning)

**When NOT to Use:**
- ❌ Free-text-only submissions with no structured fields (agent relies on field labels for source attribution)
- ❌ Submissions with heavy OCR errors (>5% error rate; agent may misparse)
- ❌ Non-English submissions (agent trained on English; performance on non-English unvalidated)
- ❌ Atypical presentations with rare terminology not in training data (agent may not recognize)

**Risks if Misused:**
- If extracted evidence is used without downstream validation (Source Verification Gate), false claims may flow through
- If agent output is treated as decision input (violates ADR-004), non-autonomous guarantee breaks (prevented by schema validation)
- If evidence extraction is used without human review, over-extraction errors may influence nurse decision

**Responsible Deployment:**
- Always flow agent output through Source Verification Gate (validates citations)
- Always include agent output in human-review context (nurse sees reasoning)
- Always escalate ambiguous cases (uncertainty flags) to physician
- Audit extracted evidence monthly for bias signals (documentation patterns by cohort)

---

## 8. Known Limitations

- ❌ **Not suitable for non-English submissions:** Model trained on English medical text; performance on other languages unvalidated
- ❌ **Atypical presentations:** Eval dataset: 15 synthetic cases covering common PA scenarios; rare or atypical presentations may see degraded extraction
- ❌ **Silent omission risk:** Some evidence may exist in submission but not be extracted (not caught by agent itself; requires human oversight)
- ❌ **Implicit clinical judgment:** Agent does not judge clinical significance; it extracts; downstream Policy Mapper + physician assign significance

---

## 9. Audit & Transparency

**Output is Logged:**
- Full `findings` JSON logged in `pre_state_record` (bilateral logger, hash-chained)
- Submitted as `findings` input to Context Retriever + Policy Mapper
- Visible in nurse review UI (nurse sees extracted evidence)
- Regulator can query audit log and inspect extraction for any case

**Reproducibility:**
- Given `submission` + frozen prompt hash + frozen model version, agent output is deterministic
- Regulator can replay case: `run_pipeline(submission)` → inspect findings

**No Autonomous Output:**
- Agent output is reasoning brief, not decision
- No `decision` or `approval` field in output schema (enforced at validation layer)

---

## 10. Appendix: References

- **Eval Report:** `eval/results/eval_report_20260529_205655.md` — source_citation_accuracy dimension results
- **Agent Implementation:** `agents/evidence_summarizer.py`
- **Prompt Hash:** `config/prompt_hashes.yaml` (locked prompt version)
- **Output Schema:** `schemas/evidence_summarizer_output.json`
- **Bilateral Logger:** `logs/bilateral_logger.py` (all evidence logged)
- **Source Verification Gate:** `gates/source_verification.py` (validates agent citations)
- **System Card:** `docs/r7_system_card.md` (end-to-end system transparency)

---

**End of Evidence Summarizer Model Card**
