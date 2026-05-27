# ADR-015: Confidence Threshold Calibration

**Status:** Accepted
**Date:** 2026-05-27
**Owner:** Jim
**Related:** ADR-007 (AI-Decision-Limit Gate), ADR-009 (Eval methodology), ADR-014 (Denial Gate unlock)
**Reserved by:** Phase 2 plan §"ADRs to Write"

---

## Context

Phase 2 adds a **Runtime Confidence Gate** (the 5th hard control, sibling of admission / source verification / AI-decision-limit / denial). The gate fires when the AI's policy-mapping output has compounding uncertainty — either `overall_signal == "ambiguous"` OR the count of `ambiguous` + `unmet` criteria exceeds a threshold.

The strategy doc §6 and §7 both call out "confidence gating" as part of the Responsible AI execution architecture: the system should refuse to assist on cases where its own assessment is insufficiently confident. This ADR governs **how the threshold gets calibrated** — not whether the gate exists (that's the gate's own design, implemented in `gates/confidence.py`).

The Phase 2 plan §"Eval Expansion" was explicit: *"Do not apply a single fixed threshold to all case types — calibrate per escalation reason."*

---

## Decision

**Single-threshold MVP, with data-driven calibration.**

Two interacting pieces:

1. **The gate** (`gates/confidence.py`) holds the threshold as a module-level constant (default = 2 ambiguous/unmet criteria). Env-tunable via `CONFIDENCE_GATE_MAX_AMBIGUOUS` for ops experimentation.

2. **The calibrator** (`eval/confidence_calibrator.py`) is a pure function that reads per-case `(ambig_count, signal, expected_should_approve)` tuples from eval data, sweeps every candidate threshold from 0 to the max observed count, and recommends the threshold that **minimizes total escalation error** (false approvals + false escalations). Ties resolve toward the lower (more conservative) threshold.

The recommendation is documented in the eval report. Changing the gate's compile-time default requires:
- Re-running calibration against fresh eval data
- Updating the module constant in `gates/confidence.py`
- Bumping the eval version (per Determinism Contract invariant 10)
- A new entry in `SCOPE_DELTAS.md`

---

## Why a single global threshold (not per-failure-mode)

Phase 2 plan called for per-failure-mode tuning. We are explicitly **not doing that in Phase 2** because:

1. **Sample size.** The current dataset is n=15. With 9 named failure modes (some occurring 0 times), per-mode calibration overfits noise.
2. **Audit defensibility.** "We picked one threshold against minimum total error on n=15" is defensible. "We picked 9 different thresholds against tiny sub-samples" invites questions we can't answer.
3. **Strategic alignment.** The build's customer anchor is the nurse, not a fine-grained policy engine. A single threshold is enough to express "the system declares this case low-confidence" — the nurse can override.

Per-failure-mode calibration moves to Phase 3 (logged in `PHASE_3_BACKLOG.md` under item #16 dataset expansion — per-mode tuning requires the larger dataset).

---

## Why minimize total error rather than weight one side

In medical PA, false approvals (the AI greenlights a case that should escalate) carry higher cost than false escalations (extra nurse review on a case that could have been approved). Standard practice would weight false approvals heavier.

For the Phase 2 calibration, we use **equal weights** because:

1. The gate already fails closed by default — if signal is ambiguous, the case escalates regardless of count. The calibrator only tunes the count threshold.
2. False approvals at the gate level are caught downstream by the nurse review — they're not terminal. The bilateral logger captures every decision; nurse review still happens.
3. Unequal weights need a calibrated cost ratio (e.g., 3× false approval = 1× false escalation). We don't have the data to justify a specific ratio. Equal weights is the honest starting point.

Cost-weighted calibration moves to Phase 3 with the dataset expansion.

---

## Calibrator interface

```python
from eval.confidence_calibrator import recommend, CalibrationRecommendation

cases = [
    {"case_id": "case_0001", "ambiguous_or_unmet_count": 0,
     "overall_signal": "meets_criteria", "expected_should_approve": True},
    {"case_id": "case_0002", "ambiguous_or_unmet_count": 3,
     "overall_signal": "ambiguous",     "expected_should_approve": False},
    # ...
]

rec = recommend(cases)
# rec.recommended_threshold              → int
# rec.confusion_at_recommendation        → ConfusionMatrix at the recommendation
# rec.confusions_per_threshold           → full sweep
# rec.skipped_cases                      → cases missing expected_should_approve
# rec.note                               → human-readable summary
```

The calibrator is a pure function. It does not write to disk, mutate global state, or call out. The eval runner reads its output and surfaces it in the report; the operator (Jim) decides whether to update the gate constant.

---

## What this ADR does NOT cover

- **The Confidence Gate itself.** That's in `gates/confidence.py`. This ADR is purely about how the gate's threshold is *picked*.
- **Per-failure-mode tuning.** Phase 3 backlog item #16 ties this to dataset expansion.
- **Cost-weighted calibration.** Same — Phase 3.
- **Auto-applying the calibrator's recommendation.** Today the operator decides. Auto-applying would require pinning the calibration model (input data, sweep range, tie-break rule) — another invariant in the Determinism Contract. Phase 3 candidate.

---

## Consequences

1. **The Confidence Gate is data-driven, not arbitrary.** Anyone asking "why threshold = 2?" gets a calibrator result file as the answer.
2. **Eval-version-pinning gains a new dimension.** Changing the threshold = re-running eval = updating the version. Same governance pattern as model.yaml.
3. **The calibrator's recommendations are reproducible.** Pure function, no side effects, deterministic given the same input cases.
4. **Per-mode tuning is preserved as a future enhancement.** The interface (`recommend()`) accepts case dicts; per-mode tuning would group cases by failure mode and call `recommend()` per group. Mechanical extension when data warrants.
