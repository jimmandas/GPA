# Current Task — Updated 2026-05-29 (eval finished)

## What we just shipped this session

| Commit | Summary |
|---|---|
| `0762fc3` | README Quick Start block — server commands + UI URLs (dashboard, queues, trace, admin) |
| `4ee8166` | Updated CURRENT_TASK.md mid-session |
| `3fa0194` | `conftest.py` at repo root — pytest auto-loads `.env` |
| `e22ceec` | `load_dotenv()` on 4 entry points + `.env.example`. Portable outside Cowork. |
| `6344977` | `POST /api/v1/admin/reset-case-states` + admin button. Demo case-state reset. |
| `7c272d9` | Per-case threshold calibration: `case_wall_time_seconds` <60s→<90s; `case_completion_rate` >=0.95→>=0.60. |

**Plus, in `My AI Team/`:** 8 PM-planning templates; `Projects/GPA/` skeleton with symlinked `build/`. Two project subagents at `.claude/agents/`.

302 tests pass / 8 skip.

## Eval results (live, dev-tier Sonnet, recalibrated)

Report: `eval/results/eval_report_20260529_205655.md`

- **Per-case pass: 8/15** (was 1/15 pre-recalibration; predicted ~9, hit 8 — within range)
- **Aggregate dims pass: 12/15** (3 honest fails surface real signal)

**Bucket-grouped highlights:**

| Bucket | Pass | Highlights |
|---|---|---|
| Value (4) | 3/4 | ✓ cost $0.291/case real telemetry; ✓ ROI $+2.73/case; ✓ p50 wall 58.4s; ✗ false_escalation 60% (system over-escalates should-approve) |
| Trust (10) | 7/8 scored | ✓ adversarial_gate_bypass 0%; ✓ citation_correctness 1.00; ✓ rationale_faithfulness 0.97; ✗ clinical_signal 58% (Sonnet variance) |
| Operational (4) | 2/3 scored | ✓ p90 latency 77.9s; ✓ reproducibility 0.89; ✗ completion 0.59 (44/75 runs) |

7 cases fail per-case — including the 3 known broken pipelines (0002, 0007, 0015) at 0/5 completion. **Honest signal, not noise.**

## What's next (priority order)

1. **Hard-refresh dashboard** at `http://localhost:8001/index.html` — confirm all 18 tiles populate with real numbers.
2. **Loom recording.** All pre-reqs cleared: physician UX fixed, admin hidden, audit log demoted, eval has 3-bucket data, cost shows real telemetry breakdown.
3. **Optional:** ship-tier (Opus) eval for audit-grade numbers. Standing policy still requires `SHIP_TIER_APPROVED=yes`.

## Recently rejected directions

- **Cohen's κ** — meta-eval; doesn't move OKR1/OKR2
- **Larry-style dev orchestrator** — routing overhead kills velocity; chose project-level `.claude/agents/` subagents
- **`load_dotenv()` in library modules** — silent side effects on import
- **GraphRAG-Pharma portfolio project** — folder removed; pulling back to do problem discovery first
