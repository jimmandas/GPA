# Current Task — Updated 2026-05-30 (session-end)

## What we just shipped this session

| Commit | Summary |
|---|---|
| `b980e28` | Portfolio deck markdown (13-slide CAIO / hiring-manager hub) |
| `ff4a9e9` | Portfolio deck `.pptx` (Google-Slides-import-ready) |
| `62aa046` | CURRENT_TASK.md mid-session update with real eval numbers |
| `0762fc3` | README Quick Start block — server commands + UI URLs |
| `3fa0194`, `e22ceec` | `conftest.py` + `load_dotenv()` on 4 entry points + `.env.example` — project now portable outside Cowork |
| `6344977`, `7c272d9` | Reset Demo Case States admin endpoint + per-case threshold recalibration |

**Also produced (off-repo):**
- Strategic analyst memo on GPA's value, outcomes, findings, insights (delivered in chat)
- Resume revisions v1 → v4 at `~/Downloads/Jim_Mandas_Resume_2026-revised-v{1..4}.docx` — **v4 is current** (Sentra-as-methodology framing, runtime governance + outcome-driven evals as the two pillars)
- Sentra (`My AI Team/`) gained: 8 PM-planning templates at `Templates/pm-planning/`, `Projects/GPA/` skeleton with symlinked `build/`

Tests still 302 pass / 8 skip.

## Latest eval (live, dev-tier Sonnet, recalibrated thresholds)

Report: `eval/results/eval_report_20260529_205655.md`

- **Per-case pass: 8/15** (was 1/15 pre-recalibration; predicted ~9, hit 8)
- **Aggregate dims pass: 12/15**
- 3 honest fails surfaced (false_escalation 60%, clinical_signal 58%, completion 59%) — root-caused to Sonnet variance; Opus would tighten
- Value bucket 3/4 · Trust 7/8 scored · Operational 2/3 scored
- Real per-case cost from SDK telemetry: **$0.291/case**

## What's next (priority order)

1. **Review v4 resume** (`~/Downloads/Jim_Mandas_Resume_2026-revised-v4.docx`) — Sentra-as-methodology framing with runtime governance + outcome-driven evals as the headline pillars. Confirm one-page fit; adjust if needed.
2. **Loom recording.** All pre-reqs cleared: live eval has real numbers, physician UX fixed, admin hidden, audit log demoted, portfolio deck ready as visual companion.
3. **Upload `PORTFOLIO_DECK.pptx`** to Google Drive → open in Google Slides → quick visual review.
4. **Optional:** ship-tier (Opus) eval for audit-grade numbers — requires `SHIP_TIER_APPROVED=yes`.

## Open questions / decisions pending

- Whether to record the Loom this week vs hold for ship-tier eval first.
- Whether the GraphRAG-Pharma portfolio project gets revisited after the discovery research Jim is doing on adjacent problems (folder was removed this session pending problem-discovery work).

## Recently rejected directions

- **Cohen's κ** — meta-eval; doesn't move OKR1/OKR2.
- **Larry-style dev orchestrator** — routing overhead kills velocity; chose project-level `.claude/agents/` subagents instead.
- **`load_dotenv()` in library modules** — silent side effects on import; entry points own env loading.
- **"Reusable components" framing in resume** — sounds like consultant deliverable; v4 cut it and leads with runtime governance + outcome-driven evals as the two pillars.
- **GraphRAG-Pharma portfolio project (this session)** — pulled back pending problem-discovery research on adjacent verticals.
