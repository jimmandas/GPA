# Current Task — Updated 2026-05-28 (late session)

## What we just shipped this session

| Commit | Summary |
|---|---|
| `0054dbe` | Physician approval UX fix (pre-filled defaults eliminating lookalike-placeholder bug) + sync stale ADR registry (015/016/018 marked ✅, were RESERVED) |
| `fcfb088` | Per-case Value + Operational dims (case_cost_usd, case_wall_time_seconds, case_completion_rate); fix unit-mode bucket attribution (`_deferred()` defaulted to Trust; decision_reproducibility now correctly Operational in unit mode too) |
| `ee921b9` | Phase 3 backlog #25 — consolidated human-eval-data program (6 layers: SME sign-off / multi-rater / panel scoring / production telemetry / red-team / preference data) |
| `2f16b30` | Real per-case cost telemetry via ContextVar collector (Phase 3 #19 pulled forward) — 4 agents capture SDK total_cost_usd + token usage; cost dim prefers real telemetry, heuristic fallback |
| `ee921b9` (also) | Templates at `~/claude/templates/pm-planning/` (00–07) for next project — drafted from GPA retro |

Tests: 302 pass / 8 skip.

## Running background jobs

**Live dev-tier eval finished** (bash ID `b3cwcbp4p`):
- Report: `eval/results/eval_report_20260529_010141.md`
- Cases run: 15
- Per-case dims passing: **1/15** ← worth investigating; could be Sonnet sensitivity
- Aggregate dims passing: **12/16**
- All 3 buckets present (Value / Trust / Operational)

Next step: glance at the report to see which per-case dims failed and on which cases — may be a real signal or could be an artifact of the unit-mode-vs-live mode difference for the new per-case telemetry dims.

## What's next (priority order)

1. **Inspect the fresh eval report's per-case failures.** Why only 1/15 passing? Sonnet variance vs. our targets, or a real regression? Check `eval/results/eval_report_20260529_010141.md` per-case sections.
2. **Hard-refresh dashboard** to confirm it now renders the fresh live data: real cost numbers in Value bucket, real completion rates in Operational bucket, real per-case cost/wall/completion in per-case tables.
3. **Decide on Loom recording timing.** Script is ready (`docs/LOOM_SCRIPT.md`). Live report is current. Physician approval UX is fixed. No remaining demo blockers I'm aware of.
4. **Decide on ship-tier eval timing.** Standing policy requires explicit approval; default is "no." Audit-grade Opus run would close the SCOPE_BASELINE "Full eval run" row. ~90–120 min wall.

## Open questions / decisions pending

- **Why 1/15 passing per-case in the fresh report?** Could be Sonnet not meeting some target Opus met; could be the new per-case dims (case_cost/wall/completion) failing thresholds; could be a regression from today's edits. Needs eyeball.
- **Apply PM planning templates to GPA structurally?** Templates exist at `~/claude/templates/pm-planning/` but are project-agnostic. Could materialize `docs/MILESTONES.md`, `docs/OPERATIONAL_CONTRACT.md`, `docs/COVERAGE_MATRIX.md` here as concrete examples. Not requested yet.

## Recently rejected directions

- **Cohen's κ on the existing dataset.** Killed 2026-05-28 as a meta-eval that doesn't move OKR1/OKR2 outcomes. ~10 person-hours for one scalar. Re-add in Phase 3 if multi-rater production data exists. See `docs/SCOPE_DELTAS.md` and Phase 3 backlog #25.
- **Relaxing physician approve requirements** (clinical_basis + guideline_citation). Held the design — every physician action carries audit-grade basis as the governance proof. Helper text now explains this instead of letting it feel like a bug.
- **Adding per-case dims to the report despite the per-case-section bloat risk.** Greenlit — Value 1 + Operational 3 + Trust 3 = 7 per-case dims, gives each case bucket-balanced visibility. Decision was: structural framing matters more than terseness.

## Demo readiness summary

- ✅ UI tested (dashboard / pipeline trace / nurse queue / physician queue / audit log / admin)
- ✅ All 5 gates wired; physician peer review functional
- ✅ 18 dims across 3 buckets in eval framework
- ✅ Latest eval report has real telemetry (not heuristic)
- ✅ Physician approval bug fixed (pre-filled defaults)
- ⚠ Per-case pass rate dropped to 1/15 on Sonnet — inspect before recording Loom
- ❌ Loom not yet recorded
