# GPA v4 System Card

**System:** Governed Prior Authorization (GPA) v4  
**Date:** 2026-05-31  
**Phase:** P2 (R7 — Transparency)  
**Audience:** Regulated buyers (health systems, insurance reviewers), regulatory counsel, compliance teams  

---

## 1. System Name & Purpose

**System:** GPA v4 — Governed Prior Authorization Pipeline

**One-line purpose:**  
An AI-assisted medical prior authorization (PA) pipeline with mandatory human oversight, tamper-evident audit logging, and fairness governance — designed for regulated-tenant deployment (e.g., hospitals, insurance companies) under CAIO-supervised risk acceptance.

**Regulatory context:**  
Designed to support FDA oversight requirements for AI-assisted clinical decision support and state medical board requirements for delegated review authority. All decisions logged and auditable. Non-autonomous denial enforced by schema.

---

## 2. System Architecture & Components

### High-Level Pipeline

```
SUBMISSION
    ↓
[Admission Gate] ← required fields check
    ↓
[AGENT 1: Evidence Summarizer] → findings
    ↓
[AGENT 2: Context Retriever] → historical context
    ↓
[AGENT 3: Policy Mapper] → policy analysis
    ↓
[AGENT 4: Reasoning Drafter] → reasoning brief
    ↓
[Confidence Gate] ← signal threshold check
    ↓
[Source Verification Gate] ← citation validity check
    ↓
[AI Decision Limit Gate] ← schema enforcement (no autonomous decision)
    ↓
[BILATERAL LOGGER] ← hash-chained write-before-emit
    ↓
NURSE REVIEW → reasoning_brief + policy_map + context
    ↓
[Nurse Decision] → approve | escalate | pend
    ↓
[Denial Gate] ← MVP: block all denials; Route: route to physician
    ↓
[PHYSICIAN QUEUE] ← escalated cases + denials (route mode)
    ↓
[Physician Review & Decision] ← final authority
    ↓
DECISION LOG (full audit trail)
```

### Components

| Component | Type | Role | Failure Mode |
|---|---|---|---|
| **Evidence Summarizer** | LLM Agent | Extracts & organizes clinical evidence | Over-extract non-findings; miss implied evidence |
| **Context Retriever** | LLM Agent | Fetches historical patient context | Hallucinate missing records; confabulate data |
| **Policy Mapper** | LLM Agent | Maps evidence to PA policy criteria | Misinterpret policy language; inconsistent application |
| **Reasoning Drafter** | LLM Agent | Synthesizes reasoning brief for human review | Rationalize inappropriate approvals; gloss over contradictions |
| **Admission Gate** | Deterministic Validation | Check required fields present | Reject valid submissions on technicality |
| **Confidence Gate** | Deterministic Threshold | Block low-signal cases (ambiguous, missing criteria) | Escalate clear cases; pass ambiguous ones |
| **Source Verification Gate** | Deterministic Schema Check | Verify all evidence cites valid submission sources | False positives on unusual source formatting |
| **AI Decision Limit Gate** | Deterministic Schema Validation | Enforce zero autonomous decisions (no `decision`, `recommendation`, `confidence` fields in agent outputs) | Hallucinated decision fields; incomplete validation |
| **Denial Gate** | Conditional Logic | MVP: block denials · Route: route to physician | Allow unreviewed denials; deny without physician decision |
| **Bilateral Logger** | Append-only JSON Log | Hash-chained audit trail (A1); write-before-emit durability guarantee | Silent write failures; tampered records undetected |
| **Physician Queue** | Stateful Queue | HITL escalation surface; holds pending cases + denial decisions | Lost escalations; duplicate processing; orphaned cases |

### Data Contracts

**Input: Submission**
```json
{
  "case_id": "string (UUID)",
  "patient": {
    "patient_id": "string (PHI-safe identifier)",
    "age": "integer",
    "conditions": ["string"]
  },
  "imaging_request": {
    "procedure_code": "string (CPT/HCPCS)",
    "indication": "string (clinical reason)",
    "modality": "string (CT, MRI, PET, etc.)"
  },
  "prior_authorizations": ["string"],
  "clinical_history": "string (free text or structured)"
}
```

**Output: Determination (post-nurse-review)**
```json
{
  "case_id": "string",
  "status": "pending_nurse_review" | "approved" | "denied" | "escalated",
  "reasoning_brief": { "supporting_evidence": [...], "uncertainty_flags": [...] },
  "policy_map": { "criteria": [...], "overall_signal": "meets_criteria" | "ambiguous" | "unmet" },
  "context": { "prior_imaging": [...], "comorbidities": [...] },
  "audit_log_ref": "path/to/decision_log/{case_id}.jsonl"
}
```

**Audit Log: Per-Case JSONL**
```jsonl
{"type": "pre_state_record", "case_id": "...", "findings_hash": "sha256:...", "prev_record_hash": "...", "at": "2026-05-31T...Z"}
{"type": "nurse_action_record", "case_id": "...", "nurse_decision": "approve", "denial_gate_mode": "block", "prev_record_hash": "...", "at": "2026-05-31T...Z"}
{"type": "physician_action_record", "case_id": "...", "physician_decision": "deny", "rationale": "...", "prev_record_hash": "...", "at": "2026-05-31T...Z"}
```

---

## 3. Governance & Oversight Architecture

### Autonomous Decision Limit (ADR-004)

**Invariant:** No AI agent outputs a decision, recommendation, or confidence assertion.

**Enforcement:**
- Schema validation at agent output layer: agents MUST NOT emit `decision`, `recommendation`, or `confidence` fields
- AI Decision Limit Gate checks every agent output; rejects violating outputs; fails the case CLOSED
- Code review: agent prompts never instruct agents to "decide" or "recommend"

**Evidence:** 0 violations across 75 pipeline runs (P1 eval).

### Human-in-the-Loop Checkpoints

1. **Nurse Review (Mandatory)**
   - Nurse receives: reasoning_brief (agent synthesis) + policy_map (criteria analysis) + context (historical data)
   - Nurse decides: approve, escalate, or pend
   - Rationale: Required, non-empty
   - Logged: nurse_action_record with decision_gate_mode

2. **Escalation (Confidence-gated)**
   - Triggers: Low-signal cases (ambiguous, missing criteria) OR nurse escalates
   - Destination: Physician Queue (HITL layer 2)
   - Logged: escalation_event in audit trail

3. **Physician Review (For Escalations + Denials in Route Mode)**
   - Physician receives: full case context + nurse rationale + audit trail
   - Physician decides: approve, deny, or return to nurse
   - Authority: Binding (final decision-maker for escalated/denied cases)
   - Logged: physician_action_record in audit trail

4. **Denial Gate (MVP vs. Route Mode)**
   - **MVP Mode (default):** All denials blocked; escalated to physician
   - **Route Mode (production, requires key management):** Denials routed to physician; physician binds decision
   - Captured in log: `denial_gate_mode` field (A2)

### Risk Acceptance & Non-Deploy Posture (R10)

**Status:** ✅ Signed by CAIO (2026-05-31)

**Key terms:**
- **Non-deployable to real-patient PHI** until demographic fairness (R4/R5) passes acceptance bar
- **CAIO veto** over widening autonomous decision rights; veto tracked in audit log (R10 requirement)
- **Three conditions:**
  1. Counsel must ratify ≥4/5 acceptance bar before lift (R10 signoff)
  2. A9 (audit-log validation for retrospective discrimination audit) must close before external fairness claims
  3. Demographic fairness (R4/R5) must demonstrate acceptable disparate-impact deltas

---

## 4. Failure Modes & Mitigations

| Failure Mode | Detection | Mitigation | Residual Risk |
|---|---|---|---|
| **Agent hallucinates evidence** | Source Verification Gate + human review | Escalation to physician; nurse override | Low (gate + 2 humans) |
| **Agent over-extracts non-findings** | Source Verification Gate | Invalid citations trigger escalation | Low (deterministic gate) |
| **Agent silent omission** (evidence exists but not extracted) | Implicit in human review; not caught by gates | Physician review layer catch-all | Medium (depends on physician attention) |
| **Audit log corrupted** | `verify_audit_log.py` (tamper detection on retrospective audit) | Hash-chain detects tampering; fail-closed on write failure | Low (A1 hash-chain verified in P1 eval) |
| **Escalation path fails silently** | None (was Eval Gap 7; fixed in A3) | Fail-closed (A3): exception propagates; case fails CLOSED | None (A3 deployed) |
| **Physician enqueue loses case** | Idempotence + audit log | Log escalation before enqueue; physician queue deduped | Low (write-before-emit + audit trail) |
| **Nurse/physician makes error** | Audit trail | Logged for retrospective review; appeal path (R8, deferred P3) | Medium (logged but not yet appealable) |
| **System treats cohorts unequally** | R4/R5 fairness testing (deferred P3) | Human oversight layer + transparent audit trail + R10 non-deploy posture | Medium-High (mitigated by non-deploy; will close in P3) |
| **Denial gate bypass (autonomous deny)** | AI Decision Limit Gate + schema validation | Schema forbids decision fields (ADR-004); gate rejects violations | None (schema enforced) |

---

## 5. Fairness & Bias Governance

### Known Risks

| Risk | Data Source | Severity | Mitigation (MVP) | Future (R4/R5) |
|---|---|---|---|---|
| **Documentation bias** | Agent eval: over-extraction from detailed notes | Medium | Human review catches over-extracts; physician final say | Prospective fairness testing on cohorts |
| **Language bias** | Agent training data: English medical text; regional/linguistic variants underrepresented | Medium | Human review; physician cultural context | Eval on diverse patient cohorts |
| **Approval-rate disparities** | Unknown; not yet tested | Unknown | Mandatory human review + physician authority | R4/R5: measure approval rates by cohort; remediate |
| **Escalation-rate disparities** | Unknown; not yet tested | Unknown | Logged for review; escalation = physician review (transparent) | R4/R5: measure escalation rates by cohort |
| **Override rates (denial→approve)** | Unknown | Unknown | Logged; physician has final say | R4/R5: measure override rates by cohort |

### Governance Posture

**Current (R10 signed):**
- Non-deployable to real-patient PHI
- CAIO veto invoked; conditions tracked
- Audit trail enables retrospective fairness audit (A9, future)
- Mandatory human oversight at every step

**Phase 3 (R4/R5):**
- Prospective fairness eval on pilot patient cohort
- Measure approval, escalation, override rates by demographics
- If disparate impact detected: remediate or govern via R10 conditions
- Only after R4/R5 pass acceptance bar does non-deploy posture lift

---

## 6. Transparency & Auditability

### Audit Trail (A1 + A2)

**What's logged:**
- Pre-state: All agent outputs + policy context + hashes of input data
- Escalation events: Reasons for escalation; gate failures
- Nurse decisions: Approval/escalation/pend + rationale + denial_gate_mode
- Physician actions: Decisions, times, rationales
- System failures: Audit log write failures, enqueue failures (all fail-closed)

**Format:** Append-only JSONL per case (`decision_log/{case_id}.jsonl`)

**Integrity:** Hash-chained (A1)
- Each record contains `prev_record_hash` (hash of previous record)
- Genesis record has sentinel: `"sha256:" + "0"*64`
- Verifiable with: `PYTHONPATH=. python verify_audit_log.py case_id`
- Detects: record mutation, reordering, deletion

**Access:** Regulator can query any case's full audit trail

### Reproducibility

**Determinism:** Given frozen model + prompt hash, outputs are deterministic
- Prompt hashes: `config/prompt_hashes.yaml` (locked per deployment)
- Model versions: Captured in telemetry
- Regulator can replay any case and inspect step-by-step reasoning

**Transparency:** Nursing + physician decisions are logged with full rationale (not opaque)

### Non-Autonomous Guarantees

**Enforcement:** Schema layer
- Agent outputs validated against JSON schema before use
- Schema forbids `decision`, `recommendation`, `confidence` fields
- Any violation causes case to fail CLOSED (not silently allowed)

**Verification:** Schema validation happens at gate layer; failures are logged + escalated

---

## 7. Known Limitations & Deferral

### Not Suitable For

- ❌ Real-patient PHI deployment (R10 non-deploy posture)
- ❌ Atypical presentations (eval dataset: 15 synthetic cases; pilot will expand coverage)
- ❌ Fairness validation across demographics (R4/R5 deferred to Phase 3; non-deploy posture holds line)
- ❌ Appeals path (R8 deferred; placeholder escalation-to-physician exists but not yet instrumented for structured review)

### Deferred to Phase 3 (Governed, Not Dropped)

| Item | Why | Mitigation | Lift Criteria |
|---|---|---|---|
| **R4/R5 — Demographic fairness** | Requires pilot patient volume; synthetic data insufficient | R10 non-deploy posture; CAIO veto; mandatory human review | Prospective fairness eval; disparate-impact testing passes bar |
| **R8 — Contestability** | Requires appeals flow; not yet instrumented | Escalation to physician (catch-all); logged | Implement appeals intake + review process |
| **R6 — Oversight metrics** | Requires real reviewer volume on real cases | Eval framework in place; metrics recorded in audit log | Instrument on pilot data; validate effectiveness |
| **A4 — Digital signature** | Requires key management decision (off-repo) | Hash-chain (A1) proves integrity; physician veto proves authenticity | Resolve key management; deploy A4 |
| **A8 — RFC 3161 timestamp** | Requires external TSA integration | Log timestamps with submission time; physician decision time captures "when" | Integrate with public TSA |

---

## 8. Buyer Due-Diligence & Next Steps

### For Regulated Buyers

**Transparency artifacts:**
- ✅ This system card
- ✅ 4 model cards (per-agent)
- ✅ R10 (risk-acceptance + non-deploy posture)
- ✅ Eval report (`eval/results/eval_report_*.md`) — per-case cost ($0.291/case), honest failures, thresholds
- ✅ Audit-log verifier (`verify_audit_log.py`) — regulator can validate tamper-evidence

**Buyer actions:**
1. **Compliance review:** Counsel reviews R10 + audit trail architecture
2. **Fairness assessment:** Run R4/R5-like testing on your patient cohort (optional; GPA will do before unblocking R10 conditions)
3. **Pilot deployment:** Start with synthetic/historical cases; escalate to real cases after fairness clearance
4. **Operator training:** Train nurses + physicians on escalation paths; document overrides
5. **Retrospective audit:** Use `verify_audit_log.py` quarterly; review physician override patterns for bias signals

### For Regulatory Counsel

**Key claims:**
- ✅ **Auditable:** Hash-chained log; regulator can verify tampering (A1)
- ✅ **Complete:** All decisions logged; nurse + physician decisions captured (A2)
- ✅ **Non-autonomous:** Schema prevents AI decisions; confirmed in P1 eval (ADR-004, 0 violations / 75 runs)
- ✅ **HITL:** Two human checkpoints (nurse + physician escalation); all escalations logged
- ⚠️ **Fair:** Unknown; deferred to R4/R5 (R10 non-deploy posture holds line; A9 audit validation pending)

**Regulatory questions this card answers:**
- "Can you prove no one tampered with case X?" → `verify_audit_log.py case_id` + audit log hashes
- "Who made the decision?" → Query audit log; full decision trail from agents → nurse → physician
- "Did the AI override a human?" → No; schema prevents autonomous decisions
- "How do I know the system is fair?" → R10 non-deploy posture; pilot fairness testing required before lift
- "What if the nurse made an error?" → Physician escalation layer + full audit trail for appeal

---

## 9. Appendix: References & Supporting Artifacts

- **R10 (Risk Acceptance):** `/Users/lauramandas/claude/projects/My AI Team/Owner's Inbox/gpa-risk-acceptance-2026-05-31/`
- **Audit Logger:** `logs/bilateral_logger.py` (A1 implementation)
- **Verify Tool:** `verify_audit_log.py` (tamper detection)
- **Bilateral Logger Tests:** `tests/test_bilateral_logger.py` (A1 validation including hash-chain tampering drill)
- **Eval Report:** `eval/results/eval_report_20260529_205655.md` (per-case cost, dimensions, honest failures, thresholds)
- **Model Cards:** `docs/r7_model_cards_*.md` (per-agent transparency)
- **Decision Log:** `decision_log/{case_id}.jsonl` (hash-chained audit trail per case)
- **Denial Gate Spec:** `docs/SCOPE_BASELINE.md` §"ADR-014" (denial gate MVP vs. route modes)
- **AI Decision Limit:** `docs/SCOPE_BASELINE.md` §"ADR-004" (schema-enforced guarantee)

---

**End of System Card**
