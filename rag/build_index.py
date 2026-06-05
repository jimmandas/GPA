"""
Build NCCN corpus vector index using LlamaIndex + Chroma (Phase 3b).

Loads YAML fixtures from policy/nccn_fixtures/, chunks them, embeds with OpenAI,
and stores in Chroma for retrieval.

Usage:
  PYTHONPATH=. python rag/build_index.py
"""

import os
import pathlib
import yaml
from typing import List, Dict

from llama_index.core import Document, VectorStoreIndex, Settings, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb


# Configuration
EMBEDDING_MODEL = "text-embedding-3-small"  # Determinism Contract invariant 11
CHROMA_DB_PATH = pathlib.Path(__file__).parent.parent / "chroma_db"
FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "policy" / "nccn_fixtures"


def load_fixtures() -> List[Dict]:
    """Load all NCCN fixture YAML files."""
    fixtures = []
    for yaml_file in FIXTURES_DIR.glob("*.yaml"):
        with open(yaml_file, "r") as f:
            fixture = yaml.safe_load(f)
            fixture["_file"] = yaml_file.stem
            fixtures.append(fixture)
    return fixtures


def build_documents(fixtures: List[Dict]) -> List[Document]:
    """Convert fixtures into LlamaIndex Document objects."""
    documents = []

    for fixture in fixtures:
        indication = fixture["indication_category"]
        modality = fixture["modality"]
        ref = fixture.get("overall_policy_reference", "")

        for criterion in fixture.get("criteria", []):
            passage_id = criterion["passage_id"]
            criterion_text = criterion["criterion_text"]
            required_evidence = criterion.get("required_evidence", [])

            # Create document with metadata for filtering
            doc_text = f"{criterion_text}\n\nRequired Evidence: {', '.join(required_evidence)}"

            doc = Document(
                text=doc_text,
                metadata={
                    "passage_id": passage_id,
                    "indication_category": indication,
                    "modality": modality,
                    "cancer_type": "nsclc",  # Phase 3b POC: NSCLC only
                    "reference": ref,
                    "source_file": fixture["_file"],
                },
            )
            documents.append(doc)

    return documents


def build_index():
    """Build and persist the Chroma vector index."""
    print(f"Loading fixtures from {FIXTURES_DIR}...")
    fixtures = load_fixtures()
    print(f"✅ Loaded {len(fixtures)} fixture files")

    print(f"Converting to LlamaIndex documents...")
    documents = build_documents(fixtures)
    print(f"✅ Created {len(documents)} documents ({sum(len(f.get('criteria', [])) for f in fixtures)} criteria total)")

    # Configure OpenAI embedding (pinned model for determinism)
    print(f"Configuring embedding model: {EMBEDDING_MODEL}")
    embed_model = OpenAIEmbedding(
        model=EMBEDDING_MODEL,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    Settings.embed_model = embed_model

    # Create Chroma client and vector store
    print(f"Initializing Chroma vector store at {CHROMA_DB_PATH}...")
    CHROMA_DB_PATH.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    vector_store = ChromaVectorStore(
        chroma_collection=client.get_or_create_collection(
            name="nccn_nsclc_v5",
            metadata={"hnsw:space": "cosine"},
        )
    )

    # Create index and insert documents — StorageContext required for Chroma persistence
    print(f"Building vector index (embedding {len(documents)} documents)...")
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )

    print(f"✅ Index built and persisted to {CHROMA_DB_PATH}")
    print(f"   Collection: nccn_nsclc_v5")
    print(f"   Documents: {len(documents)}")
    print(f"   Embedding model: {EMBEDDING_MODEL}")
    print(f"   Vector store: Chroma (persistent)")

    return index


if __name__ == "__main__":
    build_index()
