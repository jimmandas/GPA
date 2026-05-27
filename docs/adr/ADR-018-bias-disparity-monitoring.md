# ADR-018: Bias / Disparity Monitoring

**Status:** Accepted (scope-addition, 2026-05-27)
**Date:** 2026-05-27
**Owner:** Jim
**Related:** ADR-009 (Eval methodology), ADR-015 (Confidence threshold calibration)
**Status note:** This ADR is OUTSIDE the original scope/PRD/Phase 2 plan. The strategy framing doc §6 named bias monitoring as part of the Responsible AI execution architecture; user approved adding it to the GPA build's scope on 2026-05-27.

---

## Context

The strategy framing doc §6 names bias monitoring as part of the Responsible AI execution architecture: *"The platform must embed: explainability, evidence provenance, confidence gating, audit traceability, escalation controls, policy lineage, reproducibility, **bias monitoring**, human override capabilities, bounded execution controls."*

The original GPA scope and PRD did not include this. The Phase 2 plan did not include it either. This ADR captures the design and rationale for adding it.

**Why now:** Responsible AI is named as a core constraint, not a downstream concern. Bias monitoring belongs in-architecture if it belongs anywhere — adding it after the fact would mean the eval framework can't demonstrate the system was tested for systematic disparities.

---

## Decision

**Add a new aggregate eval dimension `bias_disparity` that computes per-cohort score spreads across the already-computable per-case dims.**

The cohort cuts are read from `ground_truth.jsonl`:

1. `label_category` — `clean` / `judgment_intensive` / `adversarial`
2. `indication_category` — `staging` / `post_treatment_surveillance` / etc.

The per-case dims tested for disparity are the ones that produce real per-case floats (not binary pass/fail):

- `source_citation_accuracy`
- `rationale_faithfulness`
- `decision_reproducibility`

For each (cohort_field × dim) pair, compute the spread = max(per-cohort mean) − min(per-cohort mean). If any spread exceeds **0.20**, flag systematic bias.

```
Score = 1.0 − max_observed_spread   (clipped to [0, 1])
Target = max_spread < 0.20
Notes name the worst-offending (cohort_field, dim, cohort_a, cohort_b) tuple
```

---

## Why a cohort spread (and not a more sophisticated metric)

Alternatives considered:

| Metric | Why not |
|---|---|
| Demographic parity (per protected attribute) | The synthetic fixtures don't carry race / ethnicity / SES. Demographic parity needs the data; we don't have it. |
| Equalized odds | Same problem — needs labeled positive/negative outcomes per protected group. |
| Stratified Brier score | More principled but more opaque to a non-technical reader. Spread is direct: "the system scored 1.00 on clean cases but 0.60 on adversarial — that's a 0.40 spread." |
| Worst-case slice analysis | Equivalent in practice; spread is the same number. |

**Spread is the right primitive for the available data.** It works on every dim that produces a per-case float, on every categorical cohort field, with no extra labels needed. When the dataset grows to support real demographic attributes (Phase 3), this dim becomes the floor; demographic parity becomes the ceiling.

---

## Why 0.20 threshold

This is a judgment call, not a calibrated number:

- 0.20 = "20 percentage points of score difference between cohorts"
- Looser than typical equalized-odds thresholds (~0.05 in protected-class contexts), reflecting the fact that we're operating on case-difficulty cohorts (clean vs adversarial *should* differ to some degree — adversarial cases are explicitly harder)
- Tight enough to surface real disparities. If the system scores 1.00 on clean cases and 0.60 on judgment-intensive, that's a 0.40 spread — clear flag.

**Calibration path:** The threshold lives as `_BIAS_MAX_SPREAD` in `eval/dimensions.py`. Phase 3 work could calibrate it against domain expectations (clinical-AI fairness literature has typical bounds for case-difficulty stratification).

---

## Computational notes

- Pure function. No LLM, no I/O at call time.
- Reads pre-computed per-case dim scores; does not re-run any agents.
- Cases without `label_category` or `indication_category` ground truth are skipped (the dim returns N/A if no cohort has ≥2 cases).
- Cohorts with no per-case scores are skipped (no inferred bias for empty data).

---

## What this ADR does NOT cover

- **Demographic / protected-attribute bias.** Requires synthetic data with race/ethnicity/age/sex attributes properly labeled and varied. Logged as Phase 3 — dataset expansion + demographic attribute synthesis go together.
- **Runtime bias mitigation.** This dim DETECTS disparities; it does not MITIGATE them. Mitigation (e.g., per-cohort threshold adjustment, retraining) is a Phase 3 candidate when the dataset supports it.
- **Calibrated 0.20 threshold.** The chosen value is an opinion; calibration to clinical-AI fairness literature is Phase 3.

---

## Consequences

1. **The eval framework can answer "did you test for systematic disparities?"** Yes — see `bias_disparity` dim, plus the per-cohort-per-dim spread breakdown in the eval report.
2. **Adversarial cases are expected to drag adversarial-cohort scores down.** That's the whole point of adversarial cases. The 0.20 threshold tolerates moderate degradation; the dim fails if the gap is implausibly large (signaling either a real failure mode or a bug).
3. **Per-cohort sample sizes matter.** With n=15, some cohorts have ≤3 cases. Means computed over 3 cases are noisy. The dim should be re-evaluated when the dataset expands (Phase 3 item #16 — dataset expansion to scope target).
4. **The customer story is concrete.** "We built bias detection into the eval framework, scoring across `label_category` and `indication_category` cuts. Threshold is 0.20 absolute spread." Defensible to a regulator or reviewer.
5. **Adds 1 new aggregate dim to the eval (total: 4 done + 1 pending = 5 aggregate dims).** Counts toward eval coverage; doesn't pull from any other dim's substrate.
