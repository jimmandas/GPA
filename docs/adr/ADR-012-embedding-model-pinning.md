# ADR-012: Embedding Model Pinning Strategy

**Status:** DEFERRED to Phase 3 (2026-05-27) — written during Phase 2, but RAG was cut from Phase 2 scope before this protocol was exercised against a real corpus. Protocol remains valid; activation waits for Phase 3 RAG work.
**Date:** 2026-05-27
**Owner:** Jim

---

## ⚠ Phase 2 Status Update (2026-05-27)

This ADR was authored as part of the Phase 2 RAG initiative. RAG was cut from Phase 2 (see ADR-011 status update + `SCOPE_DELTAS.md`). The embedding-pinning protocol below remains the design of record for Phase 3 — no changes — but Determinism Contract invariant 11 ("embedding model snapshot pinned") is **not currently active** because the default eval doesn't exercise RAG.

The Chroma index in this repo was built with `sentence-transformers/all-MiniLM-L6-v2` as a demonstration; the snapshot string is recorded in `config/rag_index.yaml`. That's documentation of what the demo used, not enforcement against an active production retriever.

---

## Context

When RAG goes live (Phase 2), the retriever's outputs depend on the embedding model's behavior. Two different snapshots of the same model family can produce different rankings; a model update mid-corpus invalidates the index. Without pinning:

- Reproducibility breaks across embedding model versions.
- Eval baselines silently drift if the model gets updated underneath you.
- Audit defensibility weakens: "what model produced this retrieval?" has no answer in the log.

This is structurally the same problem ADR-002 addressed for the agents' LLM model snapshot. Same solution shape: pin it, hash it, record it in the audit trail, fail fast on drift.

---

## Decision

**The embedding model snapshot is pinned in `config/rag_index.yaml` under the `embedding_model` key. Any change to that value invalidates the RAG index and requires a full rebuild + eval re-run.**

Today (Phase 2 scaffold, FixtureRetriever):

```yaml
embedding_model: "none-fixture-mode"
```

Future real-retriever values follow a precise naming convention:

```yaml
# OpenAI:
embedding_model: "openai/text-embedding-3-large-20250101"

# Voyage:
embedding_model: "voyage/voyage-3-20250115"

# Local (Hugging Face):
embedding_model: "hf/Snowflake/arctic-embed-l-v2.0"
```

The convention is `<vendor>/<model_name>[-<snapshot_date>]`. The snapshot date is required when the vendor publishes dated model versions (OpenAI, Voyage). For local models with content-addressed identity (Hugging Face), the model name alone is the identifier; the model weights hash can be added in `extra:` if reproducibility-critical.

---

## Enforcement

The `RAGIndexValidator` reads `embedding_model` from `config/rag_index.yaml` and is the authoritative reference at runtime. Any future code that calls the embedding API MUST source the model identifier from this config — not from a literal string in code.

For the real-retriever Phase 2 implementation, this means:

```python
config = load_rag_index_config(_RAG_CONFIG_PATH)
embedding_model = config.embedding_model
embeddings = client.embeddings.create(model=embedding_model, input=text)
```

If a developer changes the model identifier in code without updating the config, the corpus hash won't match (because re-embedding will produce different vectors) and the `RAGIndexValidator` will fail at the next eval run.

---

## Update Protocol

Changing the embedding model is a deliberate, audited event. Protocol:

1. Pick the new snapshot. Document why (capability gain, vendor deprecation, cost reduction, latency improvement).
2. Re-embed the entire corpus with the new model.
3. Rebuild the vector index.
4. Recompute `corpus_hash` over the indexed content.
5. Update `config/rag_index.yaml` — bump `version`, set new `embedding_model`, new `corpus_hash`, document in `notes:`.
6. Run a full eval re-baseline. Compare to prior baseline; document any moved dimension scores in the eval report.
7. Commit the config change in a single dedicated commit titled `Rotate embedding model snapshot: <old> → <new>`.

Steps 1-6 are mandatory. The git commit is the audit checkpoint.

---

## Consequences

1. **Phase 2 reproducibility extends to the retrieval layer.** Same input + same model + same corpus → same retrieval results.
2. **Embedding model updates are explicit events.** No silent vendor-side drift can corrupt the eval baseline; the validator catches any mismatch.
3. **The audit log captures embedding lineage per call.** The Policy Mapper's `agent_event.tool_calls_made[].corpus_content_hash` ties back to the registered `embedding_model` via the config.
4. **Local-model snapshots are second-class but supported.** If we use a Hugging Face model, the model name + (optionally) weights hash provides identity equivalent to a vendor snapshot date. Less crisp than `text-embedding-3-large-20250101`, but workable.
5. **Vendor lock-in is loosely coupled.** Switching from OpenAI to Voyage is a config change + corpus re-embed + audited rotation — not a code change. The retriever interface stays stable.

---

## Alternatives Considered

| Option | Reason Not Chosen |
|---|---|
| Pin in source code as a constant | Code-level changes don't trigger config-validation; no audit checkpoint. |
| Don't pin; use vendor default ("latest") | Defeats reproducibility; silent drift. |
| Pin per-environment (dev/staging/prod) | Adds complexity. The single canonical pinning matches the single-snapshot pattern for the agent LLM (ADR-002). |
| Hash the embedding weights at runtime | Expensive (multi-GB downloads), only works for local models. Vendor snapshot date is the better identifier. |

---

## Related ADRs

- ADR-002 — Agent LLM model snapshot pinning (the structural parallel)
- ADR-011 — RAG architecture and retriever interface
- ADR-013 — Corpus update policy
