"""
Tests for the PDQ RAG ingestion pipeline (ADR-019).

Network-free: exercises corpus loading + section-aware chunking against the
committed corpus JSON. Embedding/Chroma are integration concerns and not tested
here (run rag/ingest_pdq.py with OPENAI_API_KEY for the live path).
"""

import pathlib
import pytest

from rag.ingest_pdq import load_corpus, build_chunks, SECTION_TARGET_CHARS, CORPUS_PATH


def test_corpus_present_and_provenance():
    """Corpus exists and carries license/citation/source provenance (compliance)."""
    assert CORPUS_PATH.exists(), "PDQ corpus JSON must be committed for reproducible builds"
    corpus = load_corpus()
    assert corpus["cancer_type"] == "nsclc"
    assert "PDQ" in corpus["source"]
    assert "public domain" in corpus["license"].lower()
    assert "National Cancer Institute" in corpus["citation"]
    assert len(corpus["sections"]) > 10, "expected the full multi-section NSCLC summary"


def test_chunks_carry_required_metadata():
    """Every chunk must carry traceability metadata for citation + retrieval."""
    chunks = build_chunks(load_corpus())
    assert len(chunks) > 100, "real corpus should produce many chunks"
    for c in chunks:
        assert c["section_heading"], "every chunk must cite its source section"
        assert c["passage_id"].startswith("PDQ-NSCLC-")
        assert c["cancer_type"] == "nsclc"
        assert c["text"].strip()


def test_section_aware_small_section_is_single_chunk():
    """A section at/under the size target becomes exactly one chunk."""
    corpus = {
        "cancer_type": "nsclc", "source": "test",
        "sections": [{"heading": "Small Section", "level": 2, "text": "Short clinical passage." * 3}],
    }
    chunks = build_chunks(corpus)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["section_heading"] == "Small Section"


def test_section_aware_oversized_section_falls_back_to_fixed_chunking():
    """An oversized section splits into multiple chunks sharing one passage_id."""
    big = "This is a clinical sentence about NSCLC treatment. " * 200  # ~10k chars
    corpus = {
        "cancer_type": "nsclc", "source": "test",
        "sections": [{"heading": "Big Section", "level": 2, "text": big}],
    }
    chunks = build_chunks(corpus)
    assert len(chunks) > 1, "oversized section must fall back to fixed chunking"
    assert len(big) > SECTION_TARGET_CHARS
    # all sub-chunks share the section's passage_id, with incrementing chunk_index
    pids = {c["passage_id"] for c in chunks}
    assert len(pids) == 1
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunking_is_deterministic():
    """Same corpus in -> byte-identical chunks out (Determinism Contract invariant 12)."""
    corpus = load_corpus()
    a = build_chunks(corpus)
    b = build_chunks(corpus)
    assert a == b
