# ADR-013: Corpus Update Policy

**Status:** Accepted (Phase 2 scaffold)
**Date:** 2026-05-27
**Owner:** Jim

---

## Context

The NCCN corpus changes. New guideline versions get published. Indication categories get added, refined, or deprecated. Each corpus change has the potential to change retrieval results, which changes Policy Mapper outputs, which changes everything downstream.

Without an explicit update policy:

- A well-intentioned NCCN refresh silently invalidates the v1/v2/v3 eval baselines.
- "Why did the score change?" has no traceable answer — could be the LLM, could be the prompt, could be a corpus edit nobody flagged.
- Regulator question "what version of NCCN was this case scored against?" has no defensible answer.

---

## Decision

**Any change to the corpus requires four explicit steps, in order, in a single dedicated commit:**

1. **Rebuild the index** from the new corpus content (re-embed if using a vector store, or just recompute `corpus_hash` for fixture mode).
2. **Update `config/rag_index.yaml`** — bump `version`, set new `corpus_hash`, document the change in `notes:`.
3. **Re-run the full eval baseline** on the new corpus. Compare to the prior baseline.
4. **Document any moved dimension scores** in the eval report (`eval/results/v_N_corpus_update_<date>.md`).

The `RAGIndexValidator` enforces step 2 mechanically — any eval run with a mismatched corpus hash fails fast, no exceptions. Steps 1, 3, 4 are governance steps captured by the dedicated commit and the eval results file.

---

## What Counts as a Corpus Update

- Any file added, removed, or renamed under `policy/nccn_fixtures/` (and the equivalent indexed corpus when real retrieval is wired in).
- Any byte change to an existing corpus file.
- A new indication_category × modality pair being introduced.
- A guideline version bump (e.g., NCCN NSCLC v2.2025 → v3.2025).

What does NOT count (and does not require a corpus update commit):

- Adding new ground truth cases that reference existing corpus passages.
- Editing comments in the YAML files (the corpus hash treats comments as content, so this still triggers a hash flip; do it deliberately).
- Refactoring the retriever code without changing the corpus.

---

## Why So Strict

Two principles, both from the broader Determinism Contract:

1. **Eval baselines exist precisely because scores must be reproducible against a fixed substrate.** If the substrate moves silently, the baselines are lies.
2. **Audit defensibility requires per-case provenance.** When a case is reviewed months later, the question "what NCCN content backed this determination?" must have a one-line answer: "corpus_hash X, retriever_kind Y, registered in commit Z." The hash + config + commit chain provides exactly that.

The strictness also creates the right incentives. A corpus update isn't a casual chore — it's an event with consequences, so it gets the deliberation it deserves.

---

## Update Commit Template

```
Corpus rotation: NCCN NSCLC v<old> → v<new>

Scope of change:
  - <files added>
  - <files removed>
  - <files modified, with brief description>

Eval delta vs prior baseline:
  - dimension_X: <prior> → <new>
  - ...

Reason for rotation:
  - <new guideline published / fixture correction / scope expansion>

Updated config/rag_index.yaml:
  - version: vN → vN+1
  - corpus_hash: <new>
  - notes: <reason and date>

Eval results file: eval/results/corpus_rotation_<YYYYMMDD>.md
```

---

## Consequences

1. **Corpus changes are always paired with measured outcomes.** The eval report file shows exactly what moved.
2. **CI catches drift.** When the validator runs at eval start, any unregistered corpus change fails the build.
3. **The eval history is corpus-versioned.** Looking back, every eval result is anchored to a specific `corpus_hash`, so v1/v2/v3 deltas are fair comparisons.
4. **Regulator-defensible.** "Show me the audit trail for case X under NCCN guideline version Y" returns a complete answer: case_id → pipeline_result → policy_mapper agent_event → `corpus_content_hash` → registered config → git commit history.
5. **Mild cost on routine fixture edits.** A typo fix in a fixture file triggers the full rotation protocol. This is the intended friction — the protocol exists because routine edits are exactly the moments when silent baseline corruption happens.

---

## Related ADRs

- ADR-004 — Tool mocking strategy (where the per-fixture hashing originated)
- ADR-011 — RAG architecture and retriever interface
- ADR-012 — Embedding model pinning strategy
