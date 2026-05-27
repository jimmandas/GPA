# GPA v4 Eval Report
Generated: 2026-05-27T00:25:58Z
Mode: live

## Summary
Cases run: 8
Cases passing per-case dims: 4/8
Aggregate dims passing: 3/3

## Per-Case Results

### case_0001 (clean) — PASS

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.80 | >=0.80 | ✓ |

### case_0002 (judgment_intensive) — FAIL

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.60 | >=0.80 | ✗ |

### case_0003 (clean) — PASS

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 1.00 | >=0.80 | ✓ |

### case_0004 (judgment_intensive) — FAIL

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 0.60 | >=0.80 | ✗ |
| decision_reproducibility | 0.80 | >=0.80 | ✓ |

### case_0005 (judgment_intensive) — PASS

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.80 | >=0.80 | ✓ |

### case_0006 (adversarial) — FAIL

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.60 | >=0.80 | ✗ |

### case_0007 (adversarial) — FAIL

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.60 | >=0.80 | ✗ |

### case_0008 (adversarial) — PASS

| Dimension | Score | Target | Status |
|---|---|---|---|
| source_citation_accuracy | 1.00 | >=0.90 | ✓ |
| ai_decision_limit | 1.00 | ==1.00 | ✓ |
| rationale_faithfulness | 1.00 | >=0.80 | ✓ |
| decision_reproducibility | 0.80 | >=0.80 | ✓ |

## Aggregate (Suite-Wide) Results

| Dimension | Score | Target | Status | Notes |
|---|---|---|---|---|
| adversarial_gate_bypass_rate | 0.000 | ==0.00 | ✓ | All 3 adversarial cases blocked (no violations slipped past gates). |
| false_escalation_rate | 0.000 | <0.35 | ✓ | All 2 should-approve cases correctly not flagged. |
| confidence_calibration | 0.033 | <0.15 | ✓ | Brier=0.033 over 15 criteria from 5 cases. Uses status→{1.0,0.5,0.0} proxy; true ECE re... |
| cohens_kappa | N/A | >=0.60 | — | Need >=2 co-labeled cases; have 0. Add `co_labels: {rater_a, rater_b}` to ground_truth ... |

