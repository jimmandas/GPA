# Current Task — Updated 2026-05-29

## What we just shipped this session

| Commit | Summary |
|---|---|
| `3fa0194` | `conftest.py` at repo root — pytest auto-loads `.env` |
| `e22ceec` | `load_dotenv()` added to 4 entry points (runner, diagnose_sdk, diagnose_faithfulness, api/main); `.env.example` committed. Project now portable outside Cowork. |
| `6344977` | New `POST /api/v1/admin/reset-case-states` + admin UI button. Strips `nurse_action_record` / `physician_action_record` from `case_*.jsonl` while preserving agent + gate events. Demo-only. |
| `7c272d9` | Calibrated per-case thresholds against per-case noise: `case_wall_time_seconds` <60s→<90s; `case_completion_rate` >=0.95→>=0.60. Docstrings explain why per-case ≠ suite-wide thresholds. |
| `354f6f9` | L2 `CLAUDE.md` + L4 `docs/CURRENT_TASK.md` added — the project-memory loading layers. |

**Plus, in `My AI Team/`:** 8 PM-planning templates at `Templates/pm-planning/`; `Projects/GPA/` skeleton with symlinked `build/`. In repo: 2 project subagents at `.claude/agents/` (`gpa-eval-critic`, `gpa-pre-commit-reviewer`).

302 tests pass / 8 skip.

## Running background jobs

None. Live eval `bnkb9sdtv` was killed before producing output.

## What's next (priority order)

1. **Re-run live dev-tier eval** with the recalibrated thresholds. Predicted per-case pass rate: ~9/15 (vs the pre-recalibration 1/15). ~50–80 min wall.
2. **Hard-refresh dashboard** after the new report lands — confirm Value/Operational tiles show real numbers and the per-case section shows 3 buckets.
3. **Loom recording.** Script ready at `docs/LOOM_SCRIPT.md`; physician approval UX fixed; admin page hidden; audit log demoted.

## Open questions / decisions pending

- Whether to kick off the recalibrated eval now (in background; ~50–80 min) or hold until next session.
- Ship-tier eval timing — standing policy still requires explicit `SHIP_TIER_APPROVED=yes`.

## Recently rejected directions

- **Cohen's κ** — meta-eval; doesn't move OKR1/OKR2 (reaffirmed today)
- **Larry-style dev orchestrator** — routing overhead kills dev velocity. Chose project-level `.claude/agents/` subagents — invokable directly.
- **`load_dotenv()` in library modules** — silent side effects on import. Entry points own env loading.
