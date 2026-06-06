# ADR-019: Real RAG Ingestion Pipeline (NCI PDQ corpus)

**Status:** Accepted (ingestion pipeline built; live policy-mapper cutover sequenced after GT audit)
**Date:** 2026-06-06
**Owner:** Jim
**Activates:** `PHASE_3_BACKLOG.md` item #10 — "Full RAG pipeline: parse / chunk / embed / index over a real corpus"
**Supersedes corpus source of:** `rag/build_index.py` (hand-authored YAML criteria → real parsed corpus)

---

## Context

Phase 3b shipped real RAG *mechanics* (OpenAI embeddings + Chroma vector search + metadata filter) but over a **hand-authored YAML corpus of 12 criteria** — not a parsed source document. The planned parse → chunk → embed pipeline (PHASE_3_BACKLOG #10) was never built; the chunker/embedder classes exist (`rag/chunker.py`, `rag/embedder.py`) but were never wired to a document. This gap was identified twice (2026-05-27 cut, 2026-06-04 re-plan) and not delivered both times. This ADR closes it.

## Corpus decision: NCI PDQ, not NCCN

The original plan named `nscl.pdf` (NCCN NSCLC Guidelines). **Rejected on license grounds.** The NCCN PDF's EULA (page 2) states: *"you MAY NOT distribute this Content or use it with any artificial intelligence model or tool."* It is watermarked to a single licensee. Ingesting it into a RAG pipeline violates the EULA on two counts (AI use + distribution), and committing derived chunks/embeddings to this **public** repo would be distribution. For a project whose thesis is *governed, responsible AI*, that is a disqualifying own-goal — failure mode #5 (Trustworthy).

**Chosen corpus:** **NCI PDQ — Non-Small Cell Lung Cancer Treatment, Health Professional Version.**
- **License: public domain text.** NCI: *"The content of PDQ documents can be used freely as text."* US-government-funded. No non-commercial restriction, no no-derivatives clause.
- **Domain match: exact** — NSCLC treatment, the same disease GPA is built on (47 sections: classification, TNM/AJCC staging, stage-specific treatment I–IV, recurrent).
- **Access:** structured HTML at `cancer.gov/types/lung/hp/non-small-cell-lung-treatment-pdq` (also NCBI Bookshelf NBK65917).
- **Document type:** authoritative evidence *summary* (narrative + recommendations), NOT NCCN's algorithmic payer-criteria format. PDQ is the evidence base behind such criteria. This is *more* realistic for RAG (prose retrieval) but is not a drop-in for the criteria-checklist model (see Consequences).

(USPSTF considered and rejected: not public domain, non-commercial only, "no changes except fair use" clause awkward for chunking, and off-domain — preventive screening, not oncology treatment.)

## License compliance guardrails (binding)

1. **Text only.** PDQ images carry separate permissions; we ingest text, exclude images/tables-as-images.
2. **No mislabeling.** Derived chunks are attributed as *source: NCI PDQ* with the preferred citation; we do NOT claim our chunks ARE an official NCI PDQ summary (license condition).
3. **Citation carried in metadata:** *"PDQ Adult Treatment Editorial Board. PDQ Non-Small Cell Lung Cancer Treatment. Bethesda, MD: National Cancer Institute."*

## Pipeline decisions

1. **Parse:** `rag/parse_pdq.py` — **`lxml`** (open source, BSD) over the cancer.gov HTML `<article>` node; segment by `h1–h3` headings into sections; drop nav/scripts/figures/tables (text-only, per license + chunking) and sub-200-char fragments. Fetches live via `urllib` (stdlib, User-Agent header) or parses a local `--html` file. Output: `rag/pdq_corpus/nsclc_hp.json` (committed — public-domain text, with provenance). HTML chosen over PDF deliberately: cancer.gov publishes structured HTML whose heading tags drive section-aware chunking; PDF parsing (pdfplumber available as fallback) flattens that structure and is lossier. The committed JSON is the FROZEN corpus; the parser regenerates it from live source and is verified to reproduce the exact 47 sections byte-for-byte (both live-fetch and local-HTML paths).
2. **Chunk — section-aware + fixed fallback:** each section heading is a chunk boundary; sections within the target size become one chunk; oversized sections (e.g. the 170K-char Stage IV section) fall back to the existing `Chunker` (500 chars / 100 overlap, sentence-boundary split). Every chunk carries `section_heading` for citation/traceability. Chunk boundaries are deterministic (no randomness) — satisfies Determinism Contract invariant 12.
3. **Embed:** `text-embedding-3-small` (pinned — Determinism Contract invariant 11), via existing `rag/embedder.py` / LlamaIndex `OpenAIEmbedding`.
4. **Index:** Chroma, new collection `pdq_nsclc_v1`, idempotent build (delete-before-recreate — invariant 12). Metadata per chunk: `section_heading`, `cancer_type=nsclc`, `source`, `chunk_index`, `char_len`.
5. **Retrieval strategy — semantic-first, cancer_type filter only.** PDQ prose is organized by stage/topic, NOT by GPA's 4 indication categories. Forcing the old `indication_category` metadata filter onto prose would be lossy and artificial. Instead: filter by `cancer_type=nsclc`, rank by semantic similarity on a query built from classifier output (cancer_type + stage) + findings (indication_category + modality). Section heading returned as citation. This is honest prose-RAG; the `indication_category` filter was an artifact of the pre-structured YAML corpus.

## Decision: build ingestion now; sequence live policy-mapper cutover after the GT audit

The ingestion pipeline (parse→chunk→embed→Chroma + a verified retrieval demo) is built and committed in this ADR's change. The **live policy-mapper cutover is deliberately deferred**, because:

- The policy mapper's schema models **discrete criteria** (`passage_id`, `criterion_text`, `status`, `evidence_ref`) with an "all criteria met → meets_criteria" precedence. PDQ returns **prose passages**, not criteria. Cutting over changes the policy mapper's task (criteria-checklist → evidence synthesis), its output schema, and the eval dims that read criterion status (`citation_correctness`, `clinical_signal_accuracy`).
- That cutover would destabilize exactly what the **top-priority Ground-Truth Audit** (2026-06-06) and the `not_applicable` task are calibrating. Doing it mid-flight would invalidate both.
- Therefore: **GT audit → not_applicable status → confidence-gate recal → THEN evaluate prose-RAG cutover** as its own change with its own ADR addendum.

This keeps the honest claim true today — *"real RAG ingestion with section-aware chunking over a license-clean corpus, embedded into Chroma, with verified semantic retrieval"* — without forcing an architectural ripple into unstable ground.

## Consequences

- **Positive:** The "real RAG ingestion" claim becomes true and publishable. License-clean and on-domain. The licensing decision is itself a Responsible-AI credibility point. Determinism invariants 11/12 genuinely exercised over a parsed corpus.
- **Negative / deferred:** The live pipeline still serves the hand-authored YAML criteria until the cutover. Two corpora coexist transiently (`nccn_nsclc_v5` YAML criteria = live; `pdq_nsclc_v1` PDQ chunks = ingestion artifact, retrieval-demo-verified, not yet wired to policy_mapper). This is logged, not hidden.
- **Determinism:** Corpus committed as JSON with provenance; chunking deterministic; index content reproducible via idempotent rebuild. Invariant 13 (corpus-update → rebuild + eval) applies when the cutover happens.

## Alternatives considered

- **Ingest NCCN `nscl.pdf`** — rejected (EULA prohibits AI use + distribution; public repo).
- **USPSTF/CDC corpus** — rejected vs PDQ (license wrinkles and/or off-domain).
- **Full live cutover now** — rejected (destabilizes the in-flight GT audit + not_applicable work; schema/eval ripple).
- **Map PDQ sections onto the 4 indication categories** — rejected (lossy, artificial; semantic retrieval over prose is the honest approach).
