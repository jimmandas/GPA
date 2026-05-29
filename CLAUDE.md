# GPA v4 — Project CLAUDE.md (L2 in the 4-layer loading model)

This file is what Claude Code reads first when working in this repo. Keep it
short and high-signal — it auto-loads every turn.

## Read these files first (in this order)

1. **`docs/CURRENT_TASK.md`** — what we just shipped, what's next, open
   questions, running background jobs. Updated at session end. **Always read this first.**
2. **`docs/SCOPE_BASELINE.md`** — hard invariants, ADR registry, scope discipline workflow
3. **Latest commit on `main`** — `git log --oneline -5` — last material change
4. **`docs/SCOPE_DELTAS.md`** — running log of approved scope changes (recent entries first)
5. **`docs/PHASE_3_BACKLOG.md`** — what's deferred and why

For deeper context on specific topics:
- **Eval framework:** `docs/eval-methodology.md` then `docs/EVAL_WRITEUP.md`
- **Loom recording prep:** `docs/LOOM_SCRIPT.md`
- **Architecture decisions:** `docs/adr/` (19 ADRs, 000–018)

## Canonical PM docs (outside the repo)

The strategy framing, original scope, PRD, and Phase 2 plan live at:
`~/claude/projects/My AI Team/Owner's Inbox/imaging-pa-poc-scope-2026-05-22/`

| Doc | Path | Role |
|---|---|---|
| Strategy framing | `strategy-framing-v2.docx` (canonical) + `strategy-framing-v2.md` (searchable) | Vision, OKRs, runtime-governed operating model thesis |
| POC scope | `imaging-pa-poc-scope.md` | 7-week MVP plan; agents/gates/eval/timeline |
| PRD | `imaging-pa-poc-prd.md` | Detailed reqs, data contracts, acceptance criteria |
| Phase 2 plan | `phase-2-agentic-rag-plan.md` | Weeks 9–12 (RAG cut, physician workflow) |
| Strategy → MVP alignment | `strategy-to-mvp-alignment.md` | Trace claim → architectural choice |

Read these when product/scope context is unclear. Don't re-discover them — they're listed here.

## Project conventions

- **Tests:** `SKIP_INTEGRATION_TESTS=1 PYTHONPATH=. .spike-venv/bin/pytest -q` (302 should pass, 8 skip)
- **Unit-mode eval:** `SKIP_INTEGRATION_TESTS=1 PYTHONPATH=. python eval/save_report.py` (~1 sec)
- **Live dev-tier eval (Sonnet, default):** `set -a; source .env; set +a; SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/save_report.py` (~50–80 min)
- **Live ship-tier eval (Opus, requires explicit approval):** `EVAL_TIER=ship SHIP_TIER_APPROVED=yes ...` — standing policy 2026-05-28
- **API server:** `PYTHONPATH=. uvicorn api.main:app --port 8000 --reload`
- **Static UI server:** `python -m http.server 8001 --directory ui` → `http://localhost:8001/index.html`
- **Venv:** `.spike-venv/` (gitignored). If missing: `python3.11 -m venv .spike-venv && source .spike-venv/bin/activate && pip install claude-agent-sdk fastapi uvicorn jsonschema pyyaml pydantic pytest anthropic openai`

## Standing policies

- **Customer anchor: nurse reviewer.** Provider experience is OKR3 (separate strategy track), out of scope for GPA. (Decided 2026-05-27.)
- **No AI-emitted decision, ever.** `reasoning_brief.json` schema has no `decision` field. Architectural guarantee.
- **No autonomous denial.** `determination.json` accepts only `{approve, escalate}`. Denials route to physician via `PhysicianQueue`.
- **Ship-tier eval requires explicit `SHIP_TIER_APPROVED=yes`.** Default is dev-tier (Sonnet). Standing policy 2026-05-28.
- **EVAL_TIER=dev → Sonnet hard-coded** via `MODEL_SNAPSHOT_OVERRIDE`. Don't edit `config/model.yaml` for dev evals.

## Folder structure (high-signal pointers)

```
agents/             — 4 pipeline agents (evidence_summarizer, context_retriever,
                      policy_mapper [direct anthropic SDK], reasoning_drafter)
orchestrator/
  pipeline.py       — sequential coordinator; 5 gates fire here
  telemetry.py      — ContextVar collector for per-agent SDK cost / tokens (2026-05-28)
gates/              — admission, source_verification, ai_decision_limit, denial, confidence
physician_queue/    — ABC + FilePhysicianQueue + ActionRecord (Phase 2)
rag/                — PolicyRetriever ABC + FixtureRetriever (Phase 3 = real RAG)
logs/               — bilateral_logger (write-before-emit, fsync)
eval/
  dimensions.py     — 18 active dims + 4 per-case roll-ups + 3 telemetry-driven per-case
  runner.py         — EVAL_TIER gating; per-case + aggregate scoring
  ground_truth.jsonl — 15 cases (4 clean / 6 judgment-intensive / 5 adversarial)
  results/          — eval_report_<timestamp>.md (gitignored)
api/main.py         — FastAPI; CORS to UI on :8001; dashboard / eval / admin endpoints
ui/                 — static HTML hub (index.html = dashboard for hiring manager)
prompts/            — agent system prompts (hash-pinned in config/prompt_hashes.yaml)
schemas/            — JSON Schema for every agent output
tools/fixtures/     — synthetic patient + imaging + submission data
docs/               — SCOPE_BASELINE, SCOPE_DELTAS, PHASE_3_BACKLOG, eval docs, ADRs
decision_log/       — bilateral logger JSONL per case (gitignored, audit substrate)
```

## Session-end ritual (3 minutes; saves 10–15 at next session start)

Before closing a session, update `docs/CURRENT_TASK.md` with:
- What we just shipped this session (commit hashes + one-line summaries)
- What's next (next 1–3 priority items)
- Open questions / running background jobs (eval running, key decisions pending)
- Recently rejected directions + rationale

This is the L4 layer in the project-memory-loading model (see
`~/claude/templates/pm-planning/07_project_memory_loading.md` for the
full template + rationale).
