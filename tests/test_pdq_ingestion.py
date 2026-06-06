"""
Tests for the PDQ RAG ingestion pipeline (ADR-019).

Network-free: exercises corpus loading + section-aware chunking against the
committed corpus JSON. Embedding/Chroma are integration concerns and not tested
here (run rag/ingest_pdq.py with OPENAI_API_KEY for the live path).
"""

import pathlib
import pytest

from rag.ingest_pdq import load_corpus, build_chunks, SECTION_TARGET_CHARS, CORPUS_PATH
from rag.parse_pdq import extract_sections, MIN_SECTION_CHARS


# ---------------------------------------------------------------------------
# Parse stage (rag/parse_pdq.py) — network-free, exercises extract_sections()
# ---------------------------------------------------------------------------

def test_parser_segments_by_heading():
    """Headings become section boundaries; paragraphs accrue under their heading."""
    big = "A clinical sentence about NSCLC treatment and staging. " * 6  # > MIN_SECTION_CHARS
    htmldoc = f"""
    <html><body><article>
      <h2>Stage Information</h2><p>{big}</p>
      <h2>Treatment Options</h2><p>{big}</p>
    </article></body></html>
    """
    secs = extract_sections(htmldoc)
    headings = [s["heading"] for s in secs]
    assert "Stage Information" in headings
    assert "Treatment Options" in headings
    assert all(s["char_len"] >= MIN_SECTION_CHARS for s in secs)


def test_parser_drops_short_boilerplate_sections():
    """Sections under the min-char threshold are dropped (nav crumbs etc.)."""
    htmldoc = """
    <html><body><article>
      <h2>Tiny</h2><p>too short</p>
    </article></body></html>
    """
    assert extract_sections(htmldoc) == []


def test_parser_is_text_only_excludes_tables_and_scripts():
    """License + chunking: tables/scripts/figures are excluded from extracted text."""
    body = "Clinical guidance prose about lung cancer treatment options here. " * 6
    htmldoc = f"""
    <html><body><article>
      <h2>Section</h2>
      <p>{body}</p>
      <script>var secret = 'should not appear';</script>
      <table><tr><td>IMAGE_TABLE_CONTENT_X</td></tr></table>
    </article></body></html>
    """
    secs = extract_sections(htmldoc)
    joined = " ".join(s["text"] for s in secs)
    assert "secret" not in joined
    assert "IMAGE_TABLE_CONTENT_X" not in joined


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
