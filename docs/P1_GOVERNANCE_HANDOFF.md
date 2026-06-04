# P1 Governance Roadmap — Handoff to the GPA Dev Session

**Created:** 2026-05-31 · **Source:** Sentra orchestration session (`My AI Team/`, Larry) · **Decision:** move ahead on Phase 1.

**STATUS: ✅ P1 SHIPPED 2026-05-31.** All 4 P1 items delivered and tested (A1, A2, A3, R1). Tests: 303 pass / 8 skip. 

**BONUS: ✅ R7 (Transparency Cards) COMPLETE 2026-05-31.** System card + 4 model cards (per-agent). Shipped ahead of A4/A7/A8 blockers; pairs with R10. See `docs/CURRENT_TASK.md` for delivery summary.

This is the dev-side handoff for the governance roadmap that came out of the CAIO/CPO evaluation of GPA. The full PM artifacts live off-repo (paths at the bottom). This file is the build contract: scope, phases, the P1 tasks, and the validated design for the first one. Read it before starting P2 governance work.

---

## Decision (ratified 2026-05-31)

**Build Phase 1 of the governance roadmap.** Scope was cut by the owner; phases and priority were set via a GIST scoring pass (Gilad) + Opportunity Solution Tree (Torres). P1 is the "Integrity & Honesty Floor" — all dependency-free, all eval-backed.

A new CAIO specialist ("Iris") now holds a **hard veto** over widening autonomous decision rights. The R10 risk-acceptance doc (below) is the instrument that records that veto and keeps the system **non-deployable to real patients / real PHI until demographic fairness (R4/R5) passes a named bar**.

---

## Scope list (owner-cut, revised 2026-05-31)

**Admissibility (→ O1: a regulator can verify any decision is authentic, complete, untampered without trusting us):**
A1, A2, A3, ~~A4~~, A7, ~~A8~~ 
*Note: A4 (HMAC/signature) + A8 (RFC 3161 timestamp) removed 2026-05-31 (key management cost avoided; O1 defensible via A1+A2+A3+A7)*

**Trust (→ O2: show — not assert — that human oversight works and decisions are fair):**
R1, R6, R7, R8, R10

**Deferred to P3 (governed, not dropped):** R4/R5 demographic fairness testing.

## Phases (revised 2026-05-31)

| Phase | Items | Theme | Gating |
|---|---|---|---|
| **P1** | A1, A2, A3, R1, R10 | Integrity & Honesty Floor | None — dependency-free |
| **P2** | ~~A4~~, A7, ~~A8~~, R7 | Legally Admissible Authenticity + Transparency | A1 ✅ + legal review (A4/A8 removed; see scope change 2026-05-31) |
| **P3** | R6, R8, A9, R4/R5 | Demonstrated Trust at Scale | Pilot reviewer volume; R4/R5 lifts the non-deploy posture |

> **P2 scope change (2026-05-31):** A4 (HMAC/signature) and A8 (RFC 3161 timestamp) removed from scope to avoid key-management infrastructure costs. O1 (Admissibility) remains defensible via A1 (hash-chain tamper-evidence) + A2 (complete audit trail) + A3 (fail-closed HITL) + A7 (chain-of-custody legal doc). A7 now depends on A1 ✅ + legal review only (no A4 dependency). P2 now contains: **A7** chain-of-custody doc (A1 ✅ + legal review) · **R7** model/system cards (✅ shipped). P3 items unchanged: **R6** oversight metrics · **R8** contestability · **A9** validate audit log for retrospective discrimination audit · **R4/R5** demographic fairness (governed by signed R10).

## GIST priority (ICE, ranked)

A1 (729) · R10 (648) · A3 (576) · A2 (567) · R1 (567) · A7 (336) · R7 (336) · A4 (280) · R6 (240) · R8 (210) · A8 (180).
Surprise: R10 (a doc) outranks most code. A4/R6/R8/A8 sink because their confidence rests on unbuilt prerequisites (key mgmt, reviewer volume, appeals flow, TSA).

---

## P1 build tasks (this session's work)

> R10 is being handled off-repo (Remi drafted it; Iris signs). The four below are the dev-session deliverables. All four are independent — build in any order, but A1 first (it's the dependency root for all of P2).

### A1 — Hash-chain the bilateral logger + `verify_audit_log.py`  ⭐ START HERE
Tamper-evidence for the audit trail. Closes eval Gap 6.

**Validated design (Ryn, read-only investigation already done — do not re-investigate):**
- **Chain inside `commit()`** in `logs/bilateral_logger.py` — the single chokepoint all 18 call sites flow through (4 agents, `pipeline.py`, `physician_queue/queue.py`; record types: `agent_event`, `schema_validation_event`, `pre_state_record`, `nurse_action_record`, `escalation_event`). Chaining here guarantees the *entire* JSONL is chained in ~50 LOC, one file touched.
- Add `GENESIS_PREV = "sha256:" + "0"*64` sentinel and a `canonical_hash(record)` helper (sorted-keys serialization) — both reused by the verifier.
- In `commit()`: read the last record of the case file, compute its `canonical_hash`, inject `prev_record` into a **copy** of the caller's dict (never mutate the caller's object), then serialize/write/flush/fsync exactly as today. **Keep the truncate-rollback-on-fsync-failure path unchanged** — write-before-emit is the load-bearing invariant (ADR-005).
- `verify_audit_log.py` at repo root (matches `verify_*`-at-root convention): walk records in order, recompute `canonical_hash` of record N, confirm record N+1's `prev_record` matches, re-verify genesis sentinel; report PASS or first-break index + reason; exit non-zero on failure. Runnable as `PYTHONPATH=. python verify_audit_log.py <case_id-or-path>`.
- **Honest limitation to document in-code:** content hashes (`submission_hash`, etc.) are built in `pipeline.py:_build_pre_state_record`, not the logger — so the verifier proves chain integrity + record self-consistency end-to-end, and re-verifies content hashes only when source artifacts are available. That is still the tamper-evidence guarantee A1 requires.
- **Test consequence:** 3 existing tests in `tests/test_bilateral_logger.py` assert exact-dict equality (`parsed == {...}`) and **must be updated** for the new `prev_record` field. Not avoidable, not a smell.

**Validation / definition of done (the audit drill):** add a focused test — clean chain verifies PASS; mutating any record's content, or reordering/deleting a record, makes verify FAIL at the right index. (Tess owns the adversarial test if you want a second pair of eyes.)

### A2 — Persist `DENIAL_GATE_MODE` + full physician ActionRecord into per-case decision_log JSONL
ADR-014 flags both as small follow-ups. Definition of done: one query returns "who decided, under what mode" for any case.

### A3 — Make escalation-log + physician-enqueue paths fail-closed
Replace swallowed errors (`pass` / `traceback.print_exc()`) on `_log_escalation()` and the physician-enqueue path in `record_nurse_decision` with raise+audit, so no case silently leaves the HITL pipeline. Closes eval Gap 7. Definition of done: fault-injection drill — kill the enqueue path → pipeline fails CLOSED and audits it.

### R1 — Make completion-gated eval dims fail-closed
A case with 0 claims or `completion_rate=0` must score N/A or 0 on `source_citation_accuracy` and `rationale_faithfulness` — never a vacuous 1.00. Closes eval Gap 9 (grounding inflation). After the fix, re-run the eval and confirm the inflated cases now score honestly. (Owned by Remi/eval; lives in `eval/dimensions.py`.)

---

## Build rules

- Tests: `SKIP_INTEGRATION_TESTS=1 PYTHONPATH=. .spike-venv/bin/pytest -q` — expect ~302 pass / 8 skip, plus your updated + new tests. Don't regress.
- Do **not** touch agent prompts (hash-pinned in `config/prompt_hashes.yaml`).
- Do **not** commit or push unless the owner says so.
- Update this file + `docs/CURRENT_TASK.md` at session end with what shipped.

## What stays OFF-repo (orchestration session owns these)

- **R10 signature** (Iris) and **A7 legal/FRE doc** finalization (Remi + legal).
- **Milestone chart** = the canonical cross-session tracker. Update it on return.
- Decision log + Drive mirror + session log.

## Canonical PM artifacts (read for context, do not re-derive)

- CAIO/CPO eval: `~/claude/projects/My AI Team/Owner's Inbox/gpa-governance-eval-2026-05-31/gpa-cpo-caio-evaluation.md`
- GIST scoring + OST: `~/claude/projects/My AI Team/Owner's Inbox/gpa-governance-roadmap-2026-05-31/gpa-governance-gist-ost.md`
- Milestone chart: `~/claude/projects/My AI Team/Owner's Inbox/gpa-governance-roadmap-2026-05-31/milestone-chart.md`
- R10 risk-acceptance draft: `~/claude/projects/My AI Team/Owner's Inbox/gpa-risk-acceptance-2026-05-31/`
- A7 chain-of-custody draft: `~/claude/projects/My AI Team/Owner's Inbox/gpa-audit-chain-of-custody-2026-05-31/`
