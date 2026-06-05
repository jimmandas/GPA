# ADR-022: Classifier Agent Design

**Status:** PROPOSED (2026-06-05)

**Context:**

Phase 3b introduces **RAG-backed NCCN guideline retrieval** via vector search. The current 4-agent pipeline (Evidence Summarizer → Context Retriever → Policy Mapper → Reasoning Drafter) assumes static policy criteria; Policy Mapper currently looks up fixtures by a hard-coded indication category extracted from the submission.

To support multi-cancer, multi-indication guideline retrieval at scale, we need **upstream classification** that extracts:
- **Cancer type** (NSCLC, breast, colorectal, etc.)
- **Stage** (I, II, IIIA, IV, unknown, etc.)
- **ICD-10 code** (e.g., C34.1 for NSCLC)
- **Therapy line** (first-line, second-line, maintenance, adjuvant, etc.)
- **Urgency** (routine, expedited, emergent)

These become **metadata for vector search** in Policy Mapper (e.g., "find NSCLC staging criteria for Stage IIIA patient on first-line chemo") and inform **workflow routing** (escalation, physician queue, SLA timers in Phase 4+).

Currently, Evidence Summarizer extracts `indication_category` only. A new Classifier Agent sits before Evidence Summarizer to perform structured extraction of cancer type, stage, ICD, therapy, and urgency.

**Decision:**

1. **Add Classifier Agent** as the new first agent in the 5-agent pipeline (Classifier → Evidence Summarizer → Context Retriever → Policy Mapper → Reasoning Drafter).
2. **Schema:** Structured JSON with required + optional fields.
3. **Mode:** Single-turn LLM call, temperature=0, fail-closed (escalate on error).
4. **Determinism:** Pinned system prompt (hash-validated), pinned model snapshot, temperature=0.

**Design:**

### Agent placement

```
Submission (imaging_request + clinical_indication + patient_context)
        ↓
   [CLASSIFIER] ← NEW (this ADR)
        ↓ (cancer_type, stage, icd10, therapy_line, urgency, confidence)
   [EVIDENCE SUMMARIZER] (extracts findings)
        ↓
   [CONTEXT RETRIEVER] (fetches patient history)
        ↓
   [POLICY MAPPER] (vector search NCCN by cancer_type + stage, maps criteria)
        ↓
   [REASONING DRAFTER] (synthesizes with gap detection)
        ↓
   determination.json (escalate/approve, never deny)
```

### Input

Same as current submission:
```json
{
  "case_id": "demo_001",
  "imaging_request": {...},
  "clinical_indication": {...},
  "patient_context": {...}
}
```

### Output schema

```json
{
  "case_id": "<string — copy from input>",
  "cancer_type": "<enum — see rules below>",
  "stage": "<string — see rules below>",
  "icd10_code": "<string or null>",
  "therapy_line": "<enum — see rules below>",
  "urgency": "<enum — see rules below>",
  "classification_confidence": "<high | medium | low>",
  "confidence_notes": "<string — why confidence is not high, if applicable>"
}
```

### Classification rules

#### cancer_type (required, enum)

Assigned to exactly one of:
- "nsclc" — non-small cell lung cancer
- "sclc" — small cell lung cancer
- "mesothelioma"
- "other_thoracic" — other lung/thoracic malignancy
- "breast" — breast cancer
- "colorectal" — colorectal cancer
- "melanoma"
- "unknown" — cannot determine from submission

**Rule:** Search clinical_indication.diagnosis_text, clinical_indication.diagnosis_code, imaging_request.indication_text for cancer type keywords. If ambiguous or absent, use "unknown".

#### stage (required, string format)

Format: TNM descriptor or simplified stage (I, II, IIIA, IIIB, IV) or "unknown".

Examples: "I", "IIIA", "IV", "T3N1M0", "unknown".

**Rule:** Extract from clinical_indication.supporting_notes or diagnosis_code if AJCC staging is present. If not found, use "unknown".

#### icd10_code (optional, string or null)

ICD-10 code if present in clinical_indication.diagnosis_code. Otherwise null.

**Rule:** Copy verbatim from clinical_indication.diagnosis_code if it matches pattern `C\d{2}\.\d{1,2}`. Otherwise null.

#### therapy_line (required, enum)

Assigned to exactly one of:
- "first_line" — initial systemic therapy for metastatic or advanced disease
- "second_line" — therapy after first-line progression or intolerance
- "adjuvant" — systemic therapy after surgery/radiation
- "neoadjuvant" — pre-operative systemic therapy
- "maintenance" — ongoing therapy post-induction
- "none" — imaging for staging/diagnosis only, no active therapy
- "unknown" — cannot determine from submission

**Rule:** Search clinical_indication.supporting_notes for mentions of "first-line", "second-line", "adjuvant", "neoadjuvant", "maintenance", "chemo", "immunotherapy", "targeted therapy". If none found, use "none".

#### urgency (required, enum)

Assigned to exactly one of:
- "routine" — standard scheduling, no time constraint
- "expedited" — non-emergency but faster turnaround (e.g., post-treatment surveillance)
- "emergent" — urgent evaluation needed (e.g., acute symptoms, treatment response assessment)

**Rule:** Search imaging_request.indication_text + clinical_indication.supporting_notes for keywords: "urgent", "emergent", "stat", "asap", "acute", "new symptom", "change", "progression". If found, use "emergent" or "expedited" (emergent if "urgent"/"emergent"/"stat" present, else expedited if "asap"/"acute" present). Default to "routine".

#### classification_confidence (required, enum)

- "high" — all key fields (cancer_type, stage, therapy_line) are present and unambiguous
- "medium" — some fields inferred or partially ambiguous; classification is best-effort
- "low" — multiple fields missing or highly ambiguous; may need physician clarification

**Rule:** Set to "high" only if cancer_type != "unknown" AND stage != "unknown" AND therapy_line is explicit. Otherwise "medium" or "low".

### Hard constraints

- Do NOT include a "decision" field.
- Do NOT include a "recommendation" field.
- Do NOT infer cancer type, stage, or therapy line from imaging findings alone — use submission text only.
- Return ONLY the JSON object, starting with { and ending with }.

### Determinism

- **Model:** Pinned snapshot (e.g., `claude-opus-4-1-20250805` for production, `claude-sonnet-4-5-20250929` for dev)
- **Temperature:** 0
- **Max tokens:** 500
- **System prompt:** Hash-validated against config/prompt_hashes.yaml
- **Schema:** Registered in schemas/classifier.json, hash-validated

### Error handling

- **Schema validation fails:** Log error, escalate case to physician queue (fail-closed)
- **LLM call fails:** Escalate case to physician queue
- **Timeout:** Escalate case to physician queue
- **All errors:** Audit-logged via bilateral_logger before escalation

### Integration with downstream agents

1. **Evidence Summarizer:** Receives classifier output as context. Uses cancer_type + stage to inform indication_category assignment if it differs from submission.
2. **Policy Mapper:** Receives cancer_type + stage from classifier. Uses these as **metadata for vector search** to fetch the right NCCN section.
3. **Reasoning Drafter:** Receives classifier output. Uses urgency + therapy_line to flag relevant gap-detection items (e.g., "missing treatment plan confirmation" for first-line patients).

### Rationale

Why a separate agent vs. folding into Evidence Summarizer?

1. **Separation of concerns:** Classification (structured metadata) ≠ Evidence extraction (claim grounding). Different prompts, different schemas.
2. **Determinism:** Classifier output is used *before* Evidence Summarizer; if Evidence Summarizer contradicts it, we have explicit audit trail.
3. **Reusability:** Classifier is the same for all downstream workflows (Policy Mapper RAG, physician routing, SLA timers). Evidence Summarizer is case-specific.
4. **Cost:** Single LLM call upfront; if classification fails, escalate early (saves 3 downstream calls).

### Testing strategy

1. **Schema validation:** 10 synthetic cases (varied cancer types, stages, therapy lines, urgencies) → classifier output → schema validation.
2. **Classification accuracy:** Ground truth labels on the 10 cases → compare classifier output to labels → measure precision on cancer_type, stage, therapy_line.
3. **Fail-closed:** Inject invalid submission (e.g., no diagnosis_code, no indication_text) → verify escalation, audit-logged.
4. **Determinism:** 5 reps on same submission → verify byte-identical output.

### Future (Phase 4+)

- **Real staging data:** Once physician workflow captures confirmed staging, retrain/calibrate classifier thresholds.
- **Therapy line inference:** Extend to infer therapy line from prior authorization history (not just submission text).
- **Urgency routing:** Use classifier urgency + cancer type to route to express vs. standard processing lanes (SLA timers).

---

## Alternatives considered

### 1. Fold classification into Evidence Summarizer

**Pros:** One fewer agent, slightly faster.  
**Cons:** Evidence Summarizer schema becomes bloated; classification happens *after* evidence extraction, making it harder to use classification for downstream retrieval. Violates separation of concerns.

**Decision:** Rejected. Classifier is its own agent.

### 2. Use symbolic rules (no LLM) for classification

**Pros:** Zero cost, deterministic, fast.  
**Cons:** Fragile. Cancer type extraction from text is inherently ambiguous (e.g., "patient with history of breast cancer now presenting with lung lesion" — what's the primary cancer?). Rules break on every new cancer type.

**Decision:** Rejected. LLM classification is more robust; cost is minimal ($0.02-0.03/case).

### 3. Classification *after* Evidence Summarizer output (fold into Policy Mapper)

**Pros:** One fewer call; let Evidence Summarizer produce findings, then classify based on evidence.  
**Cons:** Evidence Summarizer won't know cancer type upfront, so it can't refine indication_category. Policy Mapper becomes responsible for both classification *and* policy mapping (violates separation of concerns).

**Decision:** Rejected. Classification must be upfront.

---

## Acceptance criteria

- [ ] Schema defined (schemas/classifier.json)
- [ ] System prompt written (prompts/classifier.md)
- [ ] Agent code (`agents/classifier/agent.py`) + schema validator
- [ ] Tests pass (10 synthetic cases, schema validation, fail-closed, determinism)
- [ ] Hash registered (config/prompt_hashes.yaml)
- [ ] Integrated into orchestrator pipeline (orchestrator/pipeline.py)
- [ ] Bilateral logger records classifier output before Evidence Summarizer runs
- [ ] Determinism Contract invariants 1-10 satisfied (model pinning, temp=0, prompt hash, schema validation)

---

## Implementation timeline

- **Week 13 Day 1-2:** Schema + system prompt
- **Week 13 Day 3-5:** Agent code + tests
- **Week 14 Day 1-2:** Integration + orchestrator wiring
- **Week 14 Day 3-5:** Eval validation + ADR finalization

---

## References

- ADR-000: AI-Assists / Human-Decides
- ADR-010: Policy Mapper direct Anthropic SDK (for reference on model pinning)
- ADR-021: RAG NCCN Guideline Retrieval (parent)
- SCOPE_DELTAS.md entry "Phase 3b—RAG-Enhanced NCCN Guideline Retrieval + Classifier Agent"
