# Policy Mapper — Model Card

**Agent:** Policy Mapper (Pipeline Step 3 of 4)  
**Model:** Anthropic SDK (deterministic, no LLM sampling)  
**Date:** 2026-05-31  
**Phase:** P2 (R7 — Transparency)  

---

## 1. Agent Name & Purpose

**Name:** Policy Mapper

**Purpose:** Map extracted evidence and clinical context against prior authorization (PA) policy criteria to determine whether the imaging request meets coverage standards.

**Pipeline Stage:** Step 3 of 4 (receives evidence + context)

**Role in system:** The Policy Mapper is the policy enforcement engine. It takes structured evidence (what we know) + context (patient history) and asks: "Does this case meet policy criteria for approval?" Output is a deterministic policy-match object: which criteria are met, which are unmet, and the overall signal (meets_criteria | ambiguous | unmet). The Confidence Gate uses this signal to decide whether to escalate.

---

## 2. Architecture & Design

**Model Type:** Deterministic rules engine (Anthropic SDK)

**Not an LLM-based agent.** Policy Mapper is implemented as:
- Python code with structured rules + evidence matching
- Policy criteria defined in configuration (not prompt-based)
- Deterministic evaluation: given evidence + policy, output is always the same

**Input Interface:** Receives `findings` + `context` + `policy_config`

**Output Interface:** JSON schema — structured `policy_map` object with per-criterion evaluation

**Output Schema:**
```json
{
  "policy_id": "string (e.g., 'imaging-pa-hip-replacement')",
  "criteria": [
    {
      "passage_id": "string (e.g., 'P-1', 'P-2')",
      "criterion": "string (e.g., 'Imaging indicates post-operative complications')",
      "status": "string (met | unmet | ambiguous)",
      "evidence_refs": ["string"] (references to supporting_evidence items),
      "rationale": "string (human-readable explanation)"
    }
  ],
  "overall_signal": "string (meets_criteria | ambiguous | unmet)",
  "confidence": "string (high | medium | low)",
  "schema_version": "1.0"
}
```

**Key Design Choices:**
- **Deterministic:** No LLM sampling; given evidence + policy, output is reproducible
- **Explicit criteria:** Each criterion is evaluated independently; physician sees pass/fail/ambiguous per criterion
- **Ambiguous status:** When evidence is incomplete or contradictory, criterion is marked "ambiguous" (not forced to binary)
- **Confidence scoring:** Separate from "meets_criteria"; indicates certainty in the mapping
- **No autonomous decision:** Output is policy analysis, not decision (schema forbids `decision` field)

---

## 3. Input Data & Assumptions

**Input Format:** `findings` + `context` + `policy_id`

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
  "policy_id": "string (e.g., 'imaging-pa-knee-mri')"
}
```

**Data Contract:**
- `findings` and `context` MUST be non-null (provided by earlier agents)
- `policy_id` MUST exist in policy configuration (validated at this step)
- Each supporting_evidence item MUST have `claim` + `source_ref`

**Assumptions:**
- Policy criteria are well-defined and static (policy version locked per deployment; see `config/policy_hashes.yaml`)
- Evidence matching is exact-string or semantic-similarity (no fuzzy matching; matches are logged)
- Absence of evidence = ambiguous (not automatic denial; physician sees the gap)
- Physician can interpret ambiguous results (agent surfaces uncertainty; does not resolve it)

**Policy Configuration:** Policies loaded from `config/policies/` directory; each policy has:
- `policy_id`: Unique identifier
- `criteria`: Array of {passage_id, criterion_text, required_evidence_signals}
- `approval_threshold`: "meets_criteria" if N of M criteria met

---

## 4. Output Behavior & Limitations

**Output Format:** JSON with per-criterion evaluation + overall signal

**Typical Behavior:**
- Evaluates 3–8 criteria per policy (ranges from simple policies to complex ones)
- Marks 0–3 criteria "ambiguous" (evidence unclear)
- Overall signal: "meets_criteria" (~60% of cases in P1 eval), "ambiguous" (~30%), "unmet" (~10%)
- Confidence: "high" if ≥3 criteria clearly met; "low" if ≥2 ambiguous

**Known Behaviors:**

✅ **Strengths:**
- Explicit per-criterion pass/fail (physician sees which criteria are met)
- Flags ambiguous evidence (does not force binary)
- Rationale per criterion aids human interpretation
- Reproducible (same evidence → same policy mapping)

⚠️ **Known Quirks:**
- **Exact-match evidence:** Requires evidence claims to closely match criterion language; paraphrases may not match. Example: Criterion "history of PE" may not trigger if evidence says "prior venous thromboembolism" (semantic match, not exact).
- **Absence of contradiction:** Absence of explicit contradiction (e.g., "no prior PE") is not treated as evidence for "no PE history" (conservative). Example: If prior imaging is missing and agent does not extract "no prior imaging", criterion "prior imaging absent" is marked ambiguous.
- **Confidence not accuracy:** Confidence is "high" when many criteria are clearly met, not when the policy mapping is correct (these may differ).

**Failure Modes:**

| Mode | Detection | Example | Severity |
|---|---|---|---|
| **Missed evidence match** | Implicit; caught by physician review | Criterion mentions "prior imaging"; evidence says "prior CTs" (semantic near-miss); not matched | Medium (physician sees criterion is ambiguous) |
| **Over-matching** | Source Verification Gate checks evidence; physician reviews | Criterion "elevated risk" matches overly broad evidence claim | Low (physician context corrects) |
| **Stale policy** | Not detected; policy version mismatch would cause cryptographic check failure | Policy criteria changed but system uses old version (should not happen; policy hash validates) | Low (policy hash prevents this) |
| **Ambiguous threshold not met** | Not detected at agent level; visible in nurse review | Case has 4 met + 2 ambiguous criteria; policy says "4/6 meets_criteria"; nurse must decide if ambiguous counts | Medium (nurse decision, escalated if uncertain) |

---

## 5. Fairness & Bias Considerations

**Known Bias Risks:**

| Risk | Source | Impact | Mitigation |
|---|---|---|---|
| **Policy criteria bias (training)** | Policy design: Criteria may embed clinical assumptions biased by demographics in historical approvals | Some patient populations may match criteria more/less frequently due to documentation or clinical presentation differences | Physician review layer; prospective fairness testing (R4/R5) |
| **Evidence-matching disparities** | Evidence matching: If evidence extraction is biased, policy matching inherits that bias | Cases with sparse evidence → more "ambiguous" criteria → higher escalation → depends on physician decision-making | Transparency: all ambiguous criteria flagged; physician decides override |
| **Comorbidity interaction bias** | Policy interpretation: Policy may not account for protective/confounding comorbidities in certain populations | Policy assumes "diabetes" universally indicates certain risk; may not account for well-controlled DM | Physician review layer; escalation on ambiguous cases |
| **Prior approval rate signaling** | Heuristic: Prior approval rate (from Context Retriever) may correlate with SES/insurance type | Patients with high prior approval rates may bias Policy Mapper heuristics in their favor (if present) | Policy Mapper does not use approval rate heuristic directly; physician sees it separately |

**Current Mitigations (MVP):**
- Deterministic evaluation: policy matching is rules-based, not model-based (reproducible, auditable)
- Explicit per-criterion pass/fail/ambiguous (physician sees policy evaluation in detail)
- Mandatory human review: nurse + physician review policy mapping before approval
- Escalation on ambiguous cases (physician final authority on disputed criteria)
- Full audit trail: policy_map logged with evidence references

**Deferred to Phase 3 (R4/R5):**
- Fairness testing: measure approval rates by cohort; analyze disparities in criterion satisfaction by demographics
- If disparate-impact detected: adjust policy criteria, evidence thresholds, or physician guidance
- Model card update with empirical findings

---

## 6. Performance & Calibration

**Evaluation Metric:** Not directly scored in P1 eval (informational agent)
- Note: Policy Mapper outputs inform Confidence Gate (scored) and Reasoning Drafter (scored)

**Per-Case Cost (from telemetry, P1 eval):**
- Average: $0.01/case (deterministic evaluation; no LLM calls)
- Range: $0.005–$0.02 (depends on policy complexity)
- Model: Deterministic (no LLM)

**Latency (P1 eval, 15-case eval run):**
- p50: 0.3 seconds
- p90: 0.5 seconds
- p99: 0.8 seconds

**Stability:**
- **Perfect determinism:** Given evidence + context + policy, output is always identical
- **Zero variance:** No randomness; no hallucination risk
- **Zero crash risk:** All invalid inputs caught at validation layer (fail-closed)

**Calibration:**
- Policy criteria threshold calibrated on historical approvals (policy version locked per deployment)
- Confidence scoring heuristic: high = ≥(N-1)/N criteria met; low = ≥2 ambiguous

---

## 7. Usage Recommendations

**When to Use:**
- ✅ Any case with defined policy (Policy Mapper loads policy by policy_id)
- ✅ Cases where deterministic policy evaluation is important (reproducible, auditable)
- ✅ Cases requiring explicit per-criterion pass/fail visibility (physician must review criteria)

**When NOT to Use:**
- ❌ Cases where policy criteria are being actively debated (static policy assumption invalid)
- ❌ Cases where dynamic policy thresholds are needed (policy version is frozen; would require new policy_id)

**Risks if Misused:**
- If policy evaluation is treated as automatic approval (violates non-autonomous guarantee), nurse/physician override authority is bypassed
- If policy_id is incorrect, wrong policy is evaluated (validation prevents this)
- If evidence is assumed complete, ambiguous criteria are misjudged as "unmet" (physician should not assume completeness)

**Responsible Deployment:**
- Physician should review per-criterion rationales, not just overall signal
- Ambiguous criteria should be escalated (marked for physician review)
- Policy criteria should be reviewed for bias annually or after fairness testing results
- Monthly audit for disproportionate "ambiguous" rates across cohorts (signals documentation bias or policy misalignment)

---

## 8. Known Limitations

- ❌ **Static policy:** Policy is frozen per deployment; dynamic thresholds not supported without policy version change
- ❌ **Exact-match evidence:** Criteria are matched against evidence claims; semantic near-misses may not match
- ❌ **No implicit contradiction:** Absence of finding is ambiguous (not explicit "no finding"); physician must interpret
- ❌ **Ambiguous criteria not auto-resolved:** If N of M criteria ambiguous, overall signal is "ambiguous"; physician must break tie

---

## 9. Audit & Transparency

**Output is Logged:**
- Full `policy_map` JSON logged in `pre_state_record` (bilateral logger, hash-chained)
- Submitted as input to Confidence Gate + Reasoning Drafter
- Visible in nurse review UI (nurse sees per-criterion evaluation)
- Regulator can query audit log and inspect policy mapping for any case

**Reproducibility:**
- Given `findings` + `context` + frozen policy version, output is perfectly reproducible
- Regulator can replay case and verify policy evaluation matches

**No Autonomous Output:**
- Agent output is policy analysis, not decision
- No `decision` or `approval` field in output schema
- Overall signal is "meets_criteria" (informational), not "approve" (decision)

**Policy Auditability:**
- Policy version hash (`config/policy_hashes.yaml`) locked per deployment
- Regulator can verify which policy version was applied to a case
- Any policy change → new version hash → audit trail shows which cases used which policy

---

## 10. Appendix: References

- **Agent Implementation:** `agents/policy_mapper.py` (deterministic rules engine)
- **Policy Configurations:** `config/policies/` directory
- **Policy Hash Registry:** `config/policy_hashes.yaml`
- **Output Schema:** `schemas/policy_mapper_output.json`
- **Bilateral Logger:** `logs/bilateral_logger.py`
- **Confidence Gate:** `gates/confidence.py` (uses overall_signal + confidence)
- **System Card:** `docs/r7_system_card.md`

---

**End of Policy Mapper Model Card**
