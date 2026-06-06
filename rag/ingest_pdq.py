"""
Real RAG ingestion: NCI PDQ NSCLC corpus -> section-aware chunks -> Chroma (ADR-019).

This is the parse/chunk/embed pipeline that PHASE_3_BACKLOG #10 specified and that
Phase 3b did not deliver. Source corpus is the public-domain NCI PDQ Non-Small Cell
Lung Cancer Treatment (Health Professional Version), extracted to
rag/pdq_corpus/nsclc_hp.json with provenance (license-clean; see ADR-019).

Chunking strategy (ADR-019): section-aware + fixed fallback.
  - Each PDQ section heading is a chunk boundary.
  - Sections at/under the size target become ONE chunk.
  - Oversized sections fall back to the fixed-size Chunker (500/100, sentence-split).
  - Every chunk carries section_heading for citation/traceability.
Deterministic: no randomness, stable ordering -> reproducible index (invariant 12).

Embedding: text-embedding-3-small, pinned (invariant 11).
Index: Chroma collection 'pdq_nsclc_v1', idempotent (delete-before-recreate).

Usage:
  set -a; source .env; set +a; PYTHONPATH=. python rag/ingest_pdq.py
"""

import os
import json
import pathlib
from typing import List, Dict

from llama_index.core import Document, VectorStoreIndex, Settings, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from rag.chunker import Chunker

EMBEDDING_MODEL = "text-embedding-3-small"  # Determinism Contract invariant 11
CHROMA_DB_PATH = pathlib.Path(__file__).parent.parent / "chroma_db"
CORPUS_PATH = pathlib.Path(__file__).parent / "pdq_corpus" / "nsclc_hp.json"
COLLECTION = "pdq_nsclc_v1"

# Sections at/under this many chars become a single chunk; larger ones fall back
# to the fixed-size Chunker. ~1800 chars ~= a coherent clinical passage that still
# embeds well (well under the embedding model's token limit).
SECTION_TARGET_CHARS = 1800


def load_corpus() -> Dict:
    """Load the extracted, provenance-tagged PDQ corpus."""
    with open(CORPUS_PATH, "r") as f:
        return json.load(f)


def build_chunks(corpus: Dict) -> List[Dict]:
    """Section-aware chunking with fixed fallback. Returns list of chunk dicts."""
    cancer_type = corpus.get("cancer_type", "nsclc")
    source = corpus.get("source", "NCI PDQ NSCLC")
    fallback = Chunker(chunk_size=500, overlap=100)

    chunks: List[Dict] = []
    for sec in corpus.get("sections", []):
        heading = sec["heading"]
        text = sec["text"]
        # Stable, filesystem/metadata-safe passage id from the heading.
        slug = "".join(c if c.isalnum() else "-" for c in heading.lower()).strip("-")[:60]
        passage_id = f"PDQ-NSCLC-{slug}"

        if len(text) <= SECTION_TARGET_CHARS:
            chunks.append({
                "text": text,
                "passage_id": passage_id,
                "section_heading": heading,
                "cancer_type": cancer_type,
                "source": source,
                "chunk_index": 0,
            })
        else:
            # Oversized section -> fixed fallback (deterministic sentence split).
            sub = fallback.chunk(
                text=text,
                passage_id=passage_id,
                source=source,
                indication_category="",  # not used by PDQ retrieval (semantic-first)
                cancer_type=cancer_type,
            )
            for gc in sub:
                chunks.append({
                    "text": gc.text,
                    "passage_id": passage_id,
                    "section_heading": heading,
                    "cancer_type": cancer_type,
                    "source": source,
                    "chunk_index": gc.chunk_index,
                })
    return chunks


def build_index():
    """Parse -> chunk -> embed -> Chroma. Idempotent."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY required for embeddings. `set -a; source .env; set +a`")

    print(f"Loading corpus from {CORPUS_PATH.name}...")
    corpus = load_corpus()
    print(f"  source: {corpus['source']}")
    print(f"  license: {corpus['license'][:60]}...")
    print(f"  sections: {len(corpus['sections'])}")

    print("Chunking (section-aware + fixed fallback)...")
    chunks = build_chunks(corpus)
    print(f"  -> {len(chunks)} chunks from {len(corpus['sections'])} sections")

    documents = [
        Document(
            text=c["text"],
            metadata={
                "passage_id": c["passage_id"],
                "section_heading": c["section_heading"],
                "cancer_type": c["cancer_type"],
                "source": c["source"],
                "chunk_index": c["chunk_index"],
            },
        )
        for c in chunks
    ]

    print(f"Configuring embedding model: {EMBEDDING_MODEL}")
    Settings.embed_model = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=os.getenv("OPENAI_API_KEY"))

    print(f"Initializing Chroma at {CHROMA_DB_PATH} (idempotent rebuild)...")
    CHROMA_DB_PATH.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    try:
        client.delete_collection(name=COLLECTION)
        print(f"  cleared existing '{COLLECTION}'")
    except Exception:
        pass
    vector_store = ChromaVectorStore(
        chroma_collection=client.create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print(f"Embedding {len(documents)} chunks...")
    VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)

    print(f"\n✅ PDQ ingestion complete -> Chroma collection '{COLLECTION}'")
    print(f"   chunks: {len(documents)}  |  embedding: {EMBEDDING_MODEL}  |  source: public-domain NCI PDQ")
    return len(documents)


if __name__ == "__main__":
    build_index()
