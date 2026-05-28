# GPA v4 — Governed Prior Authorization

A multi-agent prior-authorization review pipeline with bilateral audit logging,
written for the "governed agentic workflows" pattern: every agent call is
hashed, every decision is logged write-before-emit, and a per-dimension eval
harness measures the system end-to-end.

**Status (2026-05-28):** Phase 2 MVP — nurse-anchored governance proof. 5 hard
control gates (admission, source_verification, ai_decision_limit, denial,
confidence), end-to-end physician peer-review workflow, **eval framework v3 —
19 active dimensions: 12 RAI-aligned correctness dims + 4 operational
business-value dims** (TAT proxy, cost estimate, pipeline completion rate,
gate-fire sanity check). EVAL_TIER system (dev/Sonnet vs ship/Opus). Scope
baseline + delta log.

## Responsible AI eval framework (v3)

Strategy §6 names Responsible AI as a **core system constraint, not a downstream
review phase**. The eval framework v3 operationalizes this with 19 active dims:
**12 mapped to the six RAI evaluation categories** (safety, grounding, policy
compliance, HITL, explainability, fairness) plus **4 business-value /
operational dims** that close the OKR1 measurement gap (latency, cost, stability,
gate exercise).

| RAI Category | Dims Covering It |
|---|---|
| **Safety** — agent boundary violations, unsafe actions | `ai_decision_limit`, `adversarial_gate_bypass_rate` |
| **Grounding** — evidence-tied, no fabrication | `source_citation_accuracy`, `rationale_faithfulness`, `citation_correctness` (closes scope §8 Failure Mode #9) |
| **Policy Compliance** — workflow rules respected, governance not bypassed | `adversarial_gate_bypass_rate`, `physician_queue_routing_accuracy`, `physician_rationale_compliance` |
| **HITL** — human review correctly invoked, escalation appropriate | `false_escalation_rate`, `physician_queue_routing_accuracy` |
| **Explainability** — reasoning paths reconstructable, audit replay possible | `rationale_faithfulness`, `decision_reproducibility`, bilateral logger + Pipeline Trace UI |
| **Fairness** — system behaves consistently across cohorts | `bias_disparity` (ADR-018; case-difficulty cohort cuts. Demographic-attribute cuts are Phase 3) |

**Cross-vendor judge:** `rationale_faithfulness` uses GPT-4o (pinned snapshot
`gpt-4o-2024-11-20`) — different vendor from the Claude agents under test —
to avoid self-grading bias.

**Per-case Notes in the report:** every N/A score carries diagnostic detail so
the operator knows WHY a dim couldn't compute (no co-labels, judge error, empty
queue, etc.).

See `docs/eval-methodology.md` for the canonical reference and
`docs/SCOPE_DELTAS.md` for the v1 → v2 changelog.

## What's in the box

| Path | What it is |
|---|---|
| `agents/` | The four pipeline agents: evidence_summarizer, context_retriever, policy_mapper, reasoning_drafter |
| `orchestrator/pipeline.py` | Sequentially coordinates the four agents + the **five** gates |
| `gates/` | admission, source_verification, ai_decision_limit, denial, **confidence (new Phase 2)** |
| `physician_queue/` | **(Phase 2)** PhysicianQueue ABC + FilePhysicianQueue + ActionRecord for peer review workflow |
| `rag/` | PolicyRetriever ABC + FixtureRetriever (active). Real RAG pipeline is Phase 3 — see `docs/PHASE_3_BACKLOG.md` item #10 |
| `logs/bilateral_logger.py` | Write-before-emit audit log (now also receives `physician_action_record` events) |
| `eval/` | Eval harness — **19 dimensions** + ConfidenceCalibrator + EVAL_TIER system (see `docs/eval-methodology.md`) |
| `api/main.py` | FastAPI app — pipeline endpoints, nurse queue/case endpoints, audit endpoints, physician queue/action endpoints |
| `ui/*.html` | Static review UI: `queue.html` (nurse queue), `nurse_workspace.html`, `physician_queue.html`, `physician_workspace.html`, `index.html` (audit viewer). All wired to live API |
| `prompts/` | System prompts for each agent (hash-pinned in `config/prompt_hashes.yaml`) |
| `schemas/` | JSON schemas every agent output is validated against |
| `tools/fixtures/` | Test data (submissions, patient records, prior imaging) |
| `docs/SCOPE_BASELINE.md` | The Phase 2 deliverable status + hard invariants + ADR registry |
| `docs/SCOPE_DELTAS.md` | Running log of approved scope additions / removals / clarifications |
| `docs/PHASE_3_BACKLOG.md` | Items deferred beyond Phase 2 with explicit trigger conditions |
| `docs/adr/` | 19 ADRs (000–018) covering every architectural decision |

## One-time setup

Python 3.11+ is required. The repo ships with a working virtualenv at
`.spike-venv/` (gitignored). To activate it:

```bash
source .spike-venv/bin/activate
```

If the venv is missing or you want a clean one:

```bash
python3.11 -m venv .spike-venv
source .spike-venv/bin/activate
pip install claude-agent-sdk fastapi uvicorn jsonschema pyyaml pydantic pytest
```

There is no `requirements.txt` yet — those are the packages the code actually
imports.

## Sanity check: is the SDK reachable?

Always run this first when something is misbehaving. It verifies imports,
imports the evidence_summarizer agent, and makes one minimal SDK call.

```bash
python diagnose_sdk.py
```

Expect to see `ALL CHECKS PASSED` and a sample structured result. If it fails,
do not bother with the eval — fix this first.

## Run the eval

Two modes, controlled by `SKIP_INTEGRATION_TESTS`. The eval is aligned with `imaging-pa-poc-scope.md` §7 — 4 per-case dimensions + 4 suite-wide aggregate dimensions. See `docs/eval-methodology.md` for the canonical reference.

```bash
# Load OpenAI key (required for rationale_faithfulness; optional otherwise)
set -a; source .env; set +a

# Unit mode — no live SDK calls, ~1 second.
# Scores per-case dims with stub data; aggregate dims return N/A.
SKIP_INTEGRATION_TESTS=1 PYTHONPATH=. python eval/runner.py

# Live mode — runs the full pipeline 5× per case and calls the LLM judge.
# Current dataset: 15 cases (4 clean / 6 judgment-intensive / 5 adversarial).
# ~60 minutes for 15 cases (15 × 5 pipeline runs + 15 judge calls).
SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py
```

The `PYTHONPATH=.` is required — without it the module imports fail.

Output is a markdown report saved to `eval/results/eval_report_<timestamp>.md`. The **19 active dimensions** (see `docs/eval-methodology.md` for full reference):

| # | Dimension | Layer | Target |
|---|---|---|---|
| 1 | source_citation_accuracy | per-case | >=0.90 |
| 2 | ai_decision_limit | per-case | ==1.00 |
| 3 | rationale_faithfulness | per-case (LLM judge: GPT-4o snapshot `gpt-4o-2024-11-20`) | >=0.80 |
| 4 | decision_reproducibility | per-case (5× runs) | >=0.80 |
| 5 | adversarial_gate_bypass_rate | aggregate | ==0.00 |
| 6 | false_escalation_rate | aggregate | <0.35 |
| 7 | confidence_calibration | aggregate (Brier) | <0.15 |
| 8 | cohens_kappa | aggregate (needs co-labels) | >=0.60 |
| 9 | physician_queue_routing_accuracy | aggregate (Phase 2 §12) | >=0.80 |
| 10 | physician_rationale_compliance | aggregate (Phase 2 §12) | >=0.95 |
| 11 | bias_disparity | aggregate (ADR-018 scope-addition) | max spread <0.20 |
| 12 | citation_correctness | aggregate (closes scope §8 Failure Mode #9) | >=0.95 |
| 13 | pipeline_wall_time_p50_seconds | aggregate (Tier 1 business-value; TAT proxy) | <60s |
| 14 | pipeline_completion_rate | aggregate (Tier 1; production stability) | >=0.95 |
| 15 | estimated_cost_per_case_usd | aggregate (Tier 1; admin cost proxy, heuristic) | <$2.00 |
| 16 | gate_fire_distribution | aggregate (Tier 1; gate-usage sanity, informational) | — |

**Eval tiers** (ADR-017):

```bash
# Dev tier (default): Sonnet 4.5, ~50-80 min — fast iteration, dev signal only
EVAL_TIER=dev SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/save_report.py

# Ship tier: Opus 4.1 from model.yaml, ~90-120 min — audit-grade, production-fidelity
EVAL_TIER=ship SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/save_report.py
```

Always use `eval/save_report.py` (not `eval/runner.py` directly) so the report file lands on disk.

**Faithfulness judge requires OpenAI** — per scope §7, the judge must use a different vendor than the agents (avoid self-grading bias). Set `OPENAI_API_KEY` in `.env`. Without it, the dimension reports N/A with a clear note.

## Run the API

```bash
uvicorn api.main:app --reload --port 8000
```

Endpoints (see `api/main.py` for request/response shapes):

```
POST /api/v1/pa/decide           submit a case, get a determination
POST /api/v1/pa/nurse-decision   record approve/escalate/pend after review
GET  /api/v1/health              liveness
```

## Open the UI

The three HTML files in `ui/` are self-contained and call the API. Either
open them directly (`file://` in a browser) or serve them statically:

```bash
python -m http.server 8001 --directory ui
# then visit http://localhost:8001/queue.html
```

`queue.html` is the nurse queue; `nurse_workspace.html` is the per-case
review screen; `index.html` is the audit log viewer.

## Run a single case through the pipeline (no API)

Useful for debugging an agent without the API or the eval harness:

```bash
PYTHONPATH=. python -c "
import json, pathlib
from orchestrator.pipeline import run_pipeline

sub = json.loads(pathlib.Path('tools/fixtures/submissions/case_0001.json').read_text())
result = run_pipeline(sub)
print('status:', result.status)
print(json.dumps(result.determination, indent=2)[:2000] if result.determination else 'no determination')
"
```

The audit trail for the run lands in `decision_log/{case_id}.jsonl`
(gitignored).

## Run the unit tests

```bash
PYTHONPATH=. pytest -q
```

Integration tests honor the same `SKIP_INTEGRATION_TESTS` env var as the eval.

## Editing agent prompts

System prompts live in `prompts/*.md` and are hash-pinned in
`config/prompt_hashes.yaml`. The agent modules verify the hash at import
time — if you edit a prompt and forget to update the hash, the next run
raises `PromptHashMismatchError`.

The mismatch error prints the computed hash; paste that into
`config/prompt_hashes.yaml` under the appropriate agent key. This is a
deliberate audit checkpoint — every prompt edit is recorded.

## Adding a new eval case

1. Add the submission fixture at `tools/fixtures/submissions/case_NNNN.json`.
2. Add the patient fixture at `tools/fixtures/patients/{patient_id}.json` if
   it's a new patient.
3. Add the prior-imaging fixture at
   `tools/fixtures/imaging/{patient_id}_{modality}.json`.
4. Add the ground-truth record (one line) to `eval/ground_truth.jsonl`.
5. Re-run the eval.

## Environment variables

| Var | Used by | Effect |
|---|---|---|
| `SKIP_INTEGRATION_TESTS` | eval, pytest | `1` skips live SDK calls; `0` enables them |
| `PYTHONPATH` | eval, manual scripts | Must include `.` so package imports resolve |
