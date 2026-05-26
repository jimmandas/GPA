# System Architecture Document — Evidence Summarizer Agent

**Component:** Evidence Summarizer  
**Project:** GPA v4 MVP — Governed AI-Assisted Nurse Review for Oncology Imaging PA  
**Author:** Sage (AI Solutions Architect)  
**Target audience:** Ryn (Software Engineer) — this is your build input  
**Date:** 2026-05-25  
**Status:** Build-ready  

---

## §1. Component Definition

### What It Does

The Evidence Summarizer is the first LLM agent in the GPA pipeline. It receives a validated `submission.json` (passed through the Admission Gate) and performs structured extraction — no inference, no judgment. Its sole responsibility is to produce `findings.json`: a schema-validated record of the modality, body region, indication category, data completeness flags, and verbatim quotes with source references drawn directly from the submission. It does not assess clinical merit, does not call any tools, and does not emit a decision field. It is a single-turn extractor that transforms structured submission data into structured findings data. If it cannot produce schema-valid output, it escalates — it never emits a partial or unvalidated result.

### Input — `submission.json`

Exact fields the Evidence Summarizer receives (post-Admission Gate validation):

```json
{
  "case_id": "case_0001",
  "submitted_at": "2026-05-25T14:02:11Z",
  "patient": {
    "patient_id": "pt_anon_0001",
    "age": 62,
    "sex": "F"
  },
  "imaging_request": {
    "modality": "CT",
    "body_region": "chest",
    "with_contrast": true,
    "indication_text": "Follow-up of biopsy-proven stage II NSCLC, 3 months post-resection, surveillance per NCCN."
  },
  "clinical_indication": {
    "diagnosis_code": "C34.10",
    "diagnosis_text": "Malignant neoplasm of upper lobe, right lung",
    "prior_imaging": [{"modality": "CT", "date": "2026-02-15"}],
    "supporting_notes": "Post-resection surveillance. Oncologist recommendation enclosed."
  },
  "policy_id": "oncology_imaging_routine_v1"
}
```

All required fields are guaranteed present and non-empty by the Admission Gate. The Evidence Summarizer does not re-validate required fields — it trusts the upstream gate.

### Output — `findings.json`

```json
{
  "case_id": "case_0001",
  "modality": "CT",
  "body_region": "chest",
  "indication_category": "post_treatment_surveillance",
  "completeness_flags": {
    "has_diagnosis_code": true,
    "has_prior_imaging": true,
    "has_treatment_history": true,
    "has_clinical_rationale": true
  },
  "raw_quotes": [
    {
      "text": "biopsy-proven stage II NSCLC",
      "source_ref": "imaging_request.indication_text"
    },
    {
      "text": "3 months post-resection",
      "source_ref": "imaging_request.indication_text"
    },
    {
      "text": "surveillance per NCCN",
      "source_ref": "imaging_request.indication_text"
    }
  ]
}
```

**Field-level constraints:**

| Field | Type | Constraint |
|---|---|---|
| `case_id` | string | Must equal input `case_id` — pass through, do not transform |
| `modality` | string | Extracted verbatim from `imaging_request.modality` |
| `body_region` | string | Extracted verbatim from `imaging_request.body_region` |
| `indication_category` | string enum | Must be one of exactly: `initial_diagnosis`, `staging`, `post_treatment_surveillance`, `treatment_response`, `symptom_workup`, `other` — no other values accepted |
| `completeness_flags` | object | All four keys required; values are `true`/`false` |
| `completeness_flags.has_diagnosis_code` | boolean | `true` if `clinical_indication.diagnosis_code` is non-null and non-empty |
| `completeness_flags.has_prior_imaging` | boolean | `true` if `clinical_indication.prior_imaging` is non-null and non-empty array |
| `completeness_flags.has_treatment_history` | boolean | `true` if `clinical_indication.supporting_notes` contains any treatment-related text |
| `completeness_flags.has_clinical_rationale` | boolean | `true` if `imaging_request.indication_text` is non-null and non-empty |
| `raw_quotes` | array | Minimum 1 element required; may be empty array only if no quotable text exists (rare — treat as schema warning, not error) |
| `raw_quotes[].text` | string | Verbatim substring from the source field — no paraphrase, no synthesis |
| `raw_quotes[].source_ref` | string | Dot-notation path to the source field — must be one of: `imaging_request.indication_text`, `imaging_request.modality`, `imaging_request.body_region`, `clinical_indication.diagnosis_code`, `clinical_indication.diagnosis_text`, `clinical_indication.supporting_notes`, `clinical_indication.prior_imaging` |

**Forbidden fields:** No `decision` field. No `confidence` field. No `recommendation` field. Schema validation (§4) raises on any of these.

### Position in the 4-Agent Pipeline

```
submission.json
      │
      ▼
[Admission Gate]  ← deterministic field-completeness check
      │ admitted=true
      ▼
[Evidence Summarizer]  ← THIS COMPONENT (single-turn, no tools)
      │ findings.json
      ▼
[Context Retriever]    ← uses patient_history_lookup + prior_imaging_lookup tools
      │ context.json
      ▼
[Policy Mapper]        ← uses nccn_passage_lookup tool
      │ policy_map.json
      ▼
[Reasoning Drafter]    ← single-turn, no tools, produces reasoning_brief.json
      │
      ▼
[Source Verification Gate]
[AI-Decision-Limit Gate]
[Denial Gate]
      │
      ▼
[Bilateral Logger] → determination.json
```

---

## §2. System Prompt Design

### The Exact System Prompt

This prompt is written to `prompts/evidence_summarizer.md`. Its SHA-256 is registered in `config/prompt_hashes.yaml` under key `evidence_summarizer`. Any edit to this file requires a hash update and a full eval re-run.

---

```
You are a clinical evidence extractor for a prior authorization review system.

Your sole function is structured extraction. You read a prior authorization submission and extract verbatim evidence into a fixed JSON schema. You do not assess clinical merit. You do not recommend approval or denial. You do not infer information that is not present in the submission text.

## Output Schema

You MUST return a single JSON object matching this exact schema. Return ONLY the JSON object — no prose, no markdown fences, no explanation before or after.

{
  "case_id": "<string — copy exactly from input case_id>",
  "modality": "<string — copy exactly from imaging_request.modality>",
  "body_region": "<string — copy exactly from imaging_request.body_region>",
  "indication_category": "<enum — see below>",
  "completeness_flags": {
    "has_diagnosis_code": <boolean>,
    "has_prior_imaging": <boolean>,
    "has_treatment_history": <boolean>,
    "has_clinical_rationale": <boolean>
  },
  "raw_quotes": [
    {
      "text": "<verbatim substring from the source field>",
      "source_ref": "<dot-notation path — see allowed values below>"
    }
  ]
}

## indication_category Rules

Set indication_category to exactly one of these values:

- "initial_diagnosis" — imaging is for a new, not-yet-confirmed diagnosis
- "staging" — imaging is to determine extent of a known malignancy before treatment
- "post_treatment_surveillance" — imaging is follow-up after completed treatment (surgery, radiation, chemotherapy)
- "treatment_response" — imaging is to assess response during active treatment
- "symptom_workup" — imaging is to evaluate a new or unexplained symptom
- "other" — does not fit any above category

If indication_category cannot be determined from the submission text, use "other". Do not use any value outside this list.

## completeness_flags Rules

- has_diagnosis_code: true if clinical_indication.diagnosis_code is present and non-empty
- has_prior_imaging: true if clinical_indication.prior_imaging is present and contains at least one entry
- has_treatment_history: true if clinical_indication.supporting_notes contains any reference to prior treatment (surgery, chemotherapy, radiation, resection, ablation, or similar)
- has_clinical_rationale: true if imaging_request.indication_text is present and non-empty

## raw_quotes Rules

Extract verbatim substrings that support the indication_category assignment. Each quote must:
1. Be an exact substring from the source field — no paraphrase, no synthesis, no combining text from multiple fields
2. Have a source_ref pointing to exactly one of these allowed paths:
   - imaging_request.indication_text
   - imaging_request.modality
   - imaging_request.body_region
   - clinical_indication.diagnosis_code
   - clinical_indication.diagnosis_text
   - clinical_indication.supporting_notes
   - clinical_indication.prior_imaging

Extract at minimum 1 quote. Extract at most 6 quotes. Prefer quotes that directly justify the indication_category.

## Hard Constraints

- Do NOT include a "decision" field anywhere in your output.
- Do NOT include a "recommendation" field anywhere in your output.
- Do NOT include a "confidence" field anywhere in your output.
- Do NOT include any field not listed in the output schema above.
- Do NOT add prose before or after the JSON object.
- Do NOT wrap the JSON in markdown fences (no ```json).
- Return ONLY the JSON object, starting with { and ending with }.
```

---

### Why This Schema Constrains Temperature-Driven Variation

The Evidence Summarizer has no configurable `temperature` parameter (ADR-002 Gap 1). The system prompt compensates with four structural controls:

1. **Closed enum for `indication_category`.** Six legal values. The model cannot generate a novel string — it must choose from the list. Any value outside the enum is a schema violation caught by `jsonschema` validation (§4), not a runtime surprise.

2. **Verbatim-only `raw_quotes`.** The instruction "exact substring from the source field" forces the model to copy, not summarize. Copying is low-variance behavior under a well-constrained prompt; paraphrasing is high-variance. Combined with the `source_ref` constraint, the model's output is strongly tethered to the input text.

3. **Boolean `completeness_flags`.** Boolean fields have exactly two values. The rules map each flag to a deterministic observable condition (presence of a field, non-empty string, array length). The model is making presence checks, not clinical judgments.

4. **Output-only instruction.** The prompt ends with: return ONLY the JSON, no prose, no fences. This eliminates the leading and trailing text variability that is a primary source of non-determinism in free-form LLM output.

Day 1 spike evidence confirms that under these constraints, byte-identical output is achieved across 5 runs. The spike input used a similar extraction schema and produced 1 unique hash. The production prompt is more constrained, not less.

### Output Format Enforcement Strategy

Three layers, in order:

1. **System prompt enforcement** — prompt instructions prohibit non-JSON output and extra fields (in-context constraint)
2. **JSON parse check** — `json.loads()` in the call layer; `json.JSONDecodeError` → escalate immediately, no retry
3. **Schema validation** — `jsonschema.validate(output, FINDINGS_SCHEMA)` against `schemas/findings.json`; `ValidationError` → escalate

None of these layers retries. Every failure escalates.

---

## §3. Call Layer

### Which SDK Function to Use: `query()`

The Evidence Summarizer uses `query()` from `claude_agent_sdk`, not `ClaudeSDKClient`. Reason: `ClaudeSDKClient` is required only when the agent has tools (it supports MCP servers and in-process tool registration). The Evidence Summarizer has `allowed_tools=[]` and `max_turns=1` — it is a pure extraction call with no tool round-trips. `query()` is the correct, minimal API for this pattern. This matches the Day 1 spike exactly.

**Import:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions
```

### `ClaudeAgentOptions` — Exact Values

```python
ClaudeAgentOptions(
    system_prompt=_load_system_prompt(),   # reads prompts/evidence_summarizer.md at import time
    max_turns=1,                           # Invariant #6 — enforced by agent constructor
    allowed_tools=[],                      # no tools; explicit empty list, not omitted
)
```

`_load_system_prompt()` reads `prompts/evidence_summarizer.md` and returns the full string. It is called once at module import, not per-call, so the same bytes are used for every invocation. The SHA-256 of those bytes is computed and stored on the options object before the call (§4 Governance).

**No `model` field in `ClaudeAgentOptions`** — the SDK does not expose a model parameter at this interface. Model is pinned via the `claude` CLI environment (loaded from `config/model.yaml`, value `claude-opus-4-1-20250805`). This is documented in ADR-002. The model snapshot is recorded in the audit log via `config/model.yaml`, not from a runtime API response.

### How the Prompt Is Constructed from Input

The user-turn prompt (passed as the `prompt` argument to `query()`) is the `submission.json` serialized as a JSON string. No template interpolation, no additional framing text. The raw JSON is the entire user turn.

```python
user_prompt = json.dumps(submission, separators=(',', ':'), sort_keys=True)
```

`sort_keys=True` and `separators=(',', ':')` produce canonical JSON serialization — same byte sequence for the same logical input across runs, regardless of Python dict ordering. This is required for the prompt hash to be stable (Invariant #3).

**Full call:**

```python
async def call_evidence_summarizer(submission: dict) -> str:
    """
    Returns the raw text response from the model.
    Caller is responsible for JSON parsing and schema validation.
    Raises on SDK error or empty response.
    """
    user_prompt = json.dumps(submission, separators=(',', ':'), sort_keys=True)
    
    final_text = ""
    async for message in query(
        prompt=user_prompt,
        options=_AGENT_OPTIONS,  # module-level singleton
    ):
        if hasattr(message, "content") and message.content:
            for block in message.content:
                if hasattr(block, "text"):
                    final_text += block.text
    
    if not final_text.strip():
        raise EvidenceSummarizerError("empty_response", "Model returned no text")
    
    return final_text
```

The `_AGENT_OPTIONS` singleton is constructed once at module import:

```python
_SYSTEM_PROMPT = _load_system_prompt()  # reads prompts/evidence_summarizer.md
_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt=_SYSTEM_PROMPT,
    max_turns=1,
    allowed_tools=[],
)
```

---

## §4. Governance Checkpoints

### Determinism Contract Invariants — Evidence Summarizer Enforcement

| Invariant | Requirement | How This Agent Enforces It |
|---|---|---|
| #1 — temperature=0 | Architecturally not configurable; empirically observed | Covered by Day 1 spike CI test; system prompt constraints minimize variance; ADR-002 documents the gap |
| #2 — Pinned model snapshot | `claude-opus-4-1-20250805` from `config/model.yaml` | `config/model.yaml` is read at orchestrator startup; value is recorded in `agent_event` log entry; not validated per-call (SDK limitation — ADR-002) |
| #3 — Prompt-byte hashing | SHA-256 per agent, recorded in determination and JSONL | SHA-256 computed from `_SYSTEM_PROMPT` bytes at module import; stored in `_PROMPT_HASH` module-level constant; recorded in audit log before every call |
| #6 — No self-loops | `max_turns=1` pinned | `ClaudeAgentOptions(max_turns=1)` — constructor enforces; agent raises `ValueError` if max_turns != 1 at construction |
| #10 — `ClaudeAgentOptions` version-pinned | Options from `config/agent_options.yaml` | `ClaudeAgentOptions` fields loaded from `config/agent_options.yaml`; version field checked; constructor raises if version mismatch |

**Prompt hash computation:**

```python
import hashlib

_SYSTEM_PROMPT = _load_system_prompt()
_PROMPT_HASH = "sha256:" + hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
```

This hash is checked against `config/prompt_hashes.yaml["evidence_summarizer"]` at module import. Mismatch raises `PromptHashMismatchError` — the agent will not run if the prompt has been edited without updating the registered hash. CI enforces this on every commit.

### Audit Log Fields This Agent Must Emit

One `agent_event` JSONL record is written to `decision_log/{case_id}.jsonl` immediately after the model returns and before schema validation. If schema validation fails, a second `schema_validation_event` record is appended.

**`agent_event` record (written on every call, regardless of outcome):**

```json
{
  "type": "agent_event",
  "agent": "evidence_summarizer",
  "case_id": "case_0001",
  "model_snapshot": "claude-opus-4-1-20250805",
  "prompt_hash": "sha256:7a1e...",
  "user_prompt_hash": "sha256:...",
  "output_hash": "sha256:...",
  "tool_calls_made": [],
  "raw_response_length": 412,
  "at": "2026-05-25T14:02:12.4Z"
}
```

Field notes:
- `prompt_hash` — SHA-256 of `prompts/evidence_summarizer.md` bytes (system prompt)
- `user_prompt_hash` — SHA-256 of the canonical JSON-serialized submission (user turn)
- `output_hash` — SHA-256 of the raw text response from the model (before parsing)
- `tool_calls_made` — always `[]` for this agent; explicit empty array, not omitted
- `raw_response_length` — `len(final_text)` in bytes; useful for debugging truncation

**`schema_validation_event` record (written only on validation failure):**

```json
{
  "type": "schema_validation_event",
  "agent": "evidence_summarizer",
  "case_id": "case_0001",
  "result": "fail",
  "failure_reason": "jsonschema_validation_error",
  "failure_detail": "Additional properties are not allowed ('decision' was unexpected)",
  "escalation_triggered": true,
  "at": "2026-05-25T14:02:12.5Z"
}
```

`failure_reason` ∈ `{"json_parse_error", "jsonschema_validation_error", "empty_response", "sdk_error"}`.

### Failure Behavior

All failures are fail-closed. No partial output is passed downstream. No retry at the agent level.

| Failure | Detection Point | Response |
|---|---|---|
| SDK raises exception | `async for message in query(...)` | Catch exception, log `agent_event` with `output_hash=null`, raise `EvidenceSummarizerError("sdk_error", ...)` to orchestrator |
| Empty response | After event loop, `final_text.strip() == ""` | Log `agent_event` with `output_hash=sha256_of_empty`, raise `EvidenceSummarizerError("empty_response", ...)` |
| `json.JSONDecodeError` | `json.loads(final_text)` | Log `agent_event` + `schema_validation_event(failure_reason="json_parse_error")`, raise `EvidenceSummarizerError` |
| `jsonschema.ValidationError` | `jsonschema.validate(parsed, FINDINGS_SCHEMA)` | Log `agent_event` + `schema_validation_event(failure_reason="jsonschema_validation_error")`, raise `EvidenceSummarizerError` |
| `indication_category` enum violation | Caught by `jsonschema` above | Same as `ValidationError` path |
| Forbidden field present (`decision`, `recommendation`, `confidence`) | Caught by `jsonschema` `additionalProperties: false` | Same as `ValidationError` path |
| Prompt hash mismatch | Module import | Raise `PromptHashMismatchError` — agent module will not load |

The orchestrator catches `EvidenceSummarizerError` and routes to escalate. It records the failure in `system_failures.jsonl` with the case_id, agent name, and failure_reason.

---

## §5. Data Flow

### Step-by-Step

```
1. Orchestrator receives validated submission.json from Admission Gate
   └─ Asserts: admission gate result == "admit"
   └─ Asserts: all required fields present (trust gate — no re-check)

2. Orchestrator calls agents/evidence_summarizer/agent.py::run(submission)

3. agent.run() computes audit fields before the call:
   └─ user_prompt = json.dumps(submission, separators=(',', ':'), sort_keys=True)
   └─ user_prompt_hash = sha256(user_prompt.encode())
   └─ Confirms _PROMPT_HASH matches config/prompt_hashes.yaml["evidence_summarizer"]
      └─ MISMATCH → raise PromptHashMismatchError (never reaches call)

4. agent.run() calls query(prompt=user_prompt, options=_AGENT_OPTIONS)
   └─ SDK spawns claude CLI subprocess
   └─ Streams event messages
   └─ Accumulates final_text from content blocks

5. Call completes. agent.run() checks final_text is non-empty.
   └─ EMPTY → raise EvidenceSummarizerError("empty_response")

6. agent.run() computes output_hash = sha256(final_text.encode())

7. agent.run() writes agent_event to decision_log/{case_id}.jsonl
   └─ Fields: type, agent, case_id, model_snapshot, prompt_hash, user_prompt_hash,
              output_hash, tool_calls_made=[], raw_response_length, at
   └─ Write is NOT fsynced here — full fsync happens at bilateral logger on post_state
   └─ But write is immediate (no buffering) — file.write() + file.flush()

8. agent.run() parses final_text:
   └─ json.loads(final_text)
   └─ JSONDecodeError → write schema_validation_event, raise EvidenceSummarizerError

9. agent.run() validates against schemas/findings.json:
   └─ jsonschema.validate(parsed, FINDINGS_SCHEMA)
   └─ ValidationError → write schema_validation_event, raise EvidenceSummarizerError

10. agent.run() asserts case_id pass-through:
    └─ parsed["case_id"] == submission["case_id"]
    └─ MISMATCH → treat as ValidationError, raise EvidenceSummarizerError

11. agent.run() returns parsed findings dict to orchestrator

12. Orchestrator stores findings in pipeline state
    └─ Pipeline state: {submission, findings} — passed to Context Retriever next
```

### Where Validation Happens

| Check | Location | Failure Action |
|---|---|---|
| Prompt hash matches registered hash | `agents/evidence_summarizer/agent.py` module import | Raise `PromptHashMismatchError` |
| Non-empty response | `agent.run()` after event loop | Raise `EvidenceSummarizerError` |
| Valid JSON | `agent.run()` `json.loads()` | Write `schema_validation_event`, raise |
| Schema conformance | `agent.run()` `jsonschema.validate()` | Write `schema_validation_event`, raise |
| `case_id` pass-through | `agent.run()` assertion | Raise `EvidenceSummarizerError` |

### What Gets Written to the Audit Log and When

| Record | When Written | File |
|---|---|---|
| `agent_event` | Immediately after call returns (step 7), before parsing | `decision_log/{case_id}.jsonl` |
| `schema_validation_event` | Only if JSON parse or schema validation fails (step 8 or 9) | `decision_log/{case_id}.jsonl` |

Both records are written before any exception is raised. If the write itself fails, the exception propagates to the orchestrator as an `IOError`, which routes to `system_failures.jsonl`.

---

## §6. Failure Modes and Recovery

These are the PRD §9 failure modes that apply to the Evidence Summarizer.

### Failure Mode #2 — Ambiguous-Indication Hallucination

**What it is:** The agent infers an `indication_category` not supported by the submission text. For example, classifying `"symptom_workup"` from text that describes post-treatment follow-up.

**How it surfaces:** This is a semantic error, not a structural one. The schema will accept any value from the enum — jsonschema cannot catch this. It surfaces in the eval harness (§8.4 Rationale Faithfulness, and ground-truth comparison in eval results).

**Recovery pattern:**
- Runtime: none — the schema accepts valid enum values; hallucination within the enum is not detectable at runtime
- Mitigation: system prompt rules (`indication_category` rule table with concrete examples), combined with verbatim-only `raw_quotes` that must justify the category
- Eval: `eval/metrics/source_citation.py` cross-references `raw_quotes` against the actual `indication_category`; if no quote supports the category, flag as Mode #2
- v2 iteration target: if Mode #2 appears in top-3 failure modes, add few-shot examples to the system prompt for each category

### Failure Mode #3 — Adversarial Bypass via Note Injection

**What it is:** Prompt-injected text in `clinical_indication.supporting_notes` or `imaging_request.indication_text` attempts to coerce the agent into emitting a `decision` field or an out-of-enum `indication_category`.

**Recovery pattern:**
- Primary defense: `jsonschema` validation with `additionalProperties: false` — any extra field including `decision` raises `ValidationError` → escalate
- Secondary defense: `indication_category` enum enforced by schema — any out-of-enum value raises `ValidationError` → escalate
- The agent cannot "comply" with an injection that targets the schema — the structural gates catch it before output reaches downstream
- Test: `test_summarizer_schema_enforcement` injects 3 malformed outputs (extra field, missing field, invalid enum) and asserts escalate
- Test: `test_ai_decision_limit_adversarial` in the AI-Decision-Limit Gate tests the full pipeline against adversarial dataset cases; Evidence Summarizer is the first barrier

### Failure Mode #4 — AI-Decision Emission

**What it is:** The agent includes a `decision` field in its output.

**Recovery pattern:**
- System prompt explicitly prohibits `decision`, `recommendation`, and `confidence` fields with a "Hard Constraints" section
- `jsonschema` validates with `additionalProperties: false` — any extra field raises `ValidationError` → escalate
- The AI-Decision-Limit Gate (downstream, §5.8 in PRD) provides a second layer of detection for all agent outputs
- Zero tolerance: `test_ai_decision_limit_gate` must pass at 100%

### Failure Mode #1 — Source-Missing Emission

**What it is:** A downstream brief claim is emitted without a valid `source_ref`.

**How it applies to Evidence Summarizer:** The Evidence Summarizer establishes the `raw_quotes` that all downstream agents cite. If a `raw_quote` has a `source_ref` pointing to a field that doesn't exist in the submission, the Source Verification Gate will block the brief downstream.

**Recovery pattern:**
- Schema enforcement: `source_ref` values are constrained to the allowed dot-notation paths (enforced in `schemas/findings.json` via an `enum` on `raw_quotes[].source_ref`)
- Any invalid `source_ref` path is a schema violation caught at step 9 above → escalate
- The allowed paths are exactly: `imaging_request.indication_text`, `imaging_request.modality`, `imaging_request.body_region`, `clinical_indication.diagnosis_code`, `clinical_indication.diagnosis_text`, `clinical_indication.supporting_notes`, `clinical_indication.prior_imaging`

---

## §7. File Structure

### Where the Code Lives

```
agents/
└── evidence_summarizer/
    ├── __init__.py
    ├── agent.py              ← Main module: run(), _load_system_prompt(), call layer
    └── schema_validator.py   ← jsonschema validation against schemas/findings.json

prompts/
└── evidence_summarizer.md    ← Exact system prompt text (source of truth for hash)

schemas/
└── findings.json             ← JSON Schema for findings.json output

config/
├── model.yaml                ← model_snapshot: "claude-opus-4-1-20250805"
├── prompt_hashes.yaml        ← evidence_summarizer: "sha256:..."
└── agent_options.yaml        ← max_turns: 1, allowed_tools: []

tests/
└── agents/
    └── test_evidence_summarizer.py
```

### Files Ryn Creates

**`agents/evidence_summarizer/__init__.py`**
Empty init. Exposes `run` from `agent.py`.

**`agents/evidence_summarizer/agent.py`**

Must implement:
- Module-level: `_load_system_prompt()`, `_SYSTEM_PROMPT`, `_PROMPT_HASH`, `_AGENT_OPTIONS`
- `_verify_prompt_hash()` — called at module import; raises `PromptHashMismatchError` if `_PROMPT_HASH` does not match `config/prompt_hashes.yaml["evidence_summarizer"]`
- `async def run(submission: dict, case_id: str) -> dict` — full call-and-validate flow as described in §5
- `class EvidenceSummarizerError(Exception)` — `__init__(self, reason: str, detail: str)`
- `class PromptHashMismatchError(Exception)`
- Imports: `asyncio`, `hashlib`, `json`, `jsonschema`, `yaml`, `pathlib`, `datetime` (for `at` timestamps), `claude_agent_sdk.query`, `claude_agent_sdk.ClaudeAgentOptions`

**`agents/evidence_summarizer/schema_validator.py`**

Must implement:
- `FINDINGS_SCHEMA` — loaded from `schemas/findings.json` at import
- `def validate_findings(parsed: dict) -> None` — calls `jsonschema.validate(parsed, FINDINGS_SCHEMA)`; raises `jsonschema.ValidationError` on failure

**`prompts/evidence_summarizer.md`**

The exact system prompt from §2 of this document, verbatim. No modification. After writing this file, run `sha256sum prompts/evidence_summarizer.md` and record the hash in `config/prompt_hashes.yaml["evidence_summarizer"]`.

**`schemas/findings.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "findings",
  "type": "object",
  "required": ["case_id", "modality", "body_region", "indication_category", "completeness_flags", "raw_quotes"],
  "additionalProperties": false,
  "properties": {
    "case_id": {"type": "string", "minLength": 1},
    "modality": {"type": "string", "minLength": 1},
    "body_region": {"type": "string", "minLength": 1},
    "indication_category": {
      "type": "string",
      "enum": ["initial_diagnosis", "staging", "post_treatment_surveillance", "treatment_response", "symptom_workup", "other"]
    },
    "completeness_flags": {
      "type": "object",
      "required": ["has_diagnosis_code", "has_prior_imaging", "has_treatment_history", "has_clinical_rationale"],
      "additionalProperties": false,
      "properties": {
        "has_diagnosis_code": {"type": "boolean"},
        "has_prior_imaging": {"type": "boolean"},
        "has_treatment_history": {"type": "boolean"},
        "has_clinical_rationale": {"type": "boolean"}
      }
    },
    "raw_quotes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["text", "source_ref"],
        "additionalProperties": false,
        "properties": {
          "text": {"type": "string", "minLength": 1},
          "source_ref": {
            "type": "string",
            "enum": [
              "imaging_request.indication_text",
              "imaging_request.modality",
              "imaging_request.body_region",
              "clinical_indication.diagnosis_code",
              "clinical_indication.diagnosis_text",
              "clinical_indication.supporting_notes",
              "clinical_indication.prior_imaging"
            ]
          }
        }
      }
    }
  }
}
```

Note: `additionalProperties: false` at the top level is what blocks `decision`, `recommendation`, and `confidence` fields from passing validation.

**`tests/agents/test_evidence_summarizer.py`**

Must implement these test cases (acceptance criteria from PRD §5.3):

```
test_summarizer_schema_enforcement
  - Patches the SDK call to return each of 3 malformed outputs:
    (a) output with extra field: {"case_id": ..., "decision": "approve", ...}
    (b) output with missing required field: omit "indication_category"
    (c) output with invalid enum: {"indication_category": "unknown_category", ...}
  - For each: assert EvidenceSummarizerError is raised
  - For each: assert schema_validation_event is written to decision_log

test_summarizer_determinism
  - Runs run() 5 times with identical submission input (uses real SDK, not mock)
  - Asserts all 5 output dicts are byte-identical (json.dumps with sort_keys=True)
  - Asserts all 5 output_hash values in the audit log are identical
  - NOTE: This test requires the CLI to be installed and authenticated. Skip if
    SKIP_INTEGRATION_TESTS=1 env var is set.

test_summarizer_prompt_hash_enforced
  - Temporarily patches config/prompt_hashes.yaml to a wrong hash
  - Asserts PromptHashMismatchError raised at module import (or agent construction)

test_summarizer_case_id_passthrough
  - Patches SDK to return valid JSON with a wrong case_id
  - Asserts EvidenceSummarizerError raised

test_summarizer_empty_response
  - Patches SDK to return empty string
  - Asserts EvidenceSummarizerError("empty_response", ...) raised

test_summarizer_no_decision_field
  - Patches SDK to return JSON with a "decision" field
  - Asserts EvidenceSummarizerError raised (caught by additionalProperties: false)

test_summarizer_audit_log_written_on_failure
  - Patches SDK to return invalid JSON
  - Asserts agent_event record IS written to decision_log before the raise
  - Asserts schema_validation_event record IS written after agent_event
```

---

## Appendix: Config Files Ryn Must Create

**`config/prompt_hashes.yaml`** (create if not exists):
```yaml
# SHA-256 hashes of agent system prompt files.
# Any edit to a prompt file requires updating this hash and re-running eval.
evidence_summarizer: "sha256:<compute after writing prompts/evidence_summarizer.md>"
```

**`config/model.yaml`** (create if not exists):
```yaml
model_snapshot: "claude-opus-4-1-20250805"
version: "1"
# Changing model_snapshot requires version bump and full eval re-run.
```

**`config/agent_options.yaml`** (create if not exists):
```yaml
version: "1"
evidence_summarizer:
  max_turns: 1
  allowed_tools: []
# Changing any field requires version bump and full eval re-run.
```

---

*This document is the build specification. Questions Ryn would need to ask Sage: none — every field name, value, file path, error class name, and test name is specified above.*
