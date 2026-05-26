# GPA v4 — Governed Prior Authorization

A multi-agent prior-authorization review pipeline with bilateral audit logging,
written for the "governed agentic workflows" pattern: every agent call is
hashed, every decision is logged write-before-emit, and a per-dimension eval
harness measures the system end-to-end.

## What's in the box

| Path | What it is |
|---|---|
| `agents/` | The four pipeline agents: evidence_summarizer, context_retriever, policy_mapper, reasoning_drafter |
| `orchestrator/pipeline.py` | Sequentially coordinates the four agents + the four gates |
| `gates/` | admission, source_verification, ai_decision_limit, denial |
| `logs/bilateral_logger.py` | Write-before-emit audit log |
| `eval/` | Eval harness — 8 dimensions over ground-truth cases |
| `api/main.py` | FastAPI app exposing the pipeline as HTTP endpoints |
| `ui/*.html` | Static review UI (audit log, queue, nurse workspace) |
| `prompts/` | System prompts for each agent (hash-pinned in `config/prompt_hashes.yaml`) |
| `schemas/` | JSON schemas every agent output is validated against |
| `tools/fixtures/` | Test data (submissions, patient records, prior imaging) |

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

Two modes, controlled by `SKIP_INTEGRATION_TESTS`:

```bash
# Unit mode — no live SDK calls, ~1 second.
# Scores only the 6 dimensions that don't need a live run.
SKIP_INTEGRATION_TESTS=1 PYTHONPATH=. python eval/runner.py

# Live mode — runs the full pipeline 5× per case and calls the LLM judge.
# ~10 minutes for the current 2-case ground truth. ~42 SDK calls.
SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py
```

The `PYTHONPATH=.` is required — without it the module imports fail.

Output is a markdown report printed to stdout. The 8 dimensions are:

| # | Dimension | Computed in | Target |
|---|---|---|---|
| 1 | source_citation_accuracy | both modes | >=0.90 |
| 2 | ai_decision_limit | both modes | ==1.00 |
| 3 | gate_bypass_rate | both modes | ==0.00 |
| 4 | schema_compliance | both modes | ==1.00 |
| 5 | uncertainty_flag_coverage | both modes | per case |
| 6 | overall_signal_match | both modes (stubbed in unit) | ==1.00 |
| 7 | rationale_faithfulness | live mode only (LLM judge) | >=0.80 |
| 8 | decision_reproducibility | live mode only (5× runs) | >=0.80 |

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
