"""
Chroma-based NCCN retriever for Phase 3b RAG (LlamaIndex + Chroma).

Queries the NCCN corpus index by cancer type, indication, and semantic similarity.
Returns ranked passages for Policy Mapper to evaluate against patient evidence.
"""

import os
import pathlib
from typing import List, Dict

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb


CHROMA_DB_PATH = pathlib.Path(__file__).parent.parent / "chroma_db"
EMBEDDING_MODEL = "text-embedding-3-small"


class ChromaNcclnRetriever:
    """Retrieve NCCN guideline criteria from Chroma vector store."""

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Path to Chroma persistent DB. Defaults to chroma_db/ in repo root.
        """
        self.db_path = db_path or str(CHROMA_DB_PATH)

        # Load Chroma index
        embed_model = OpenAIEmbedding(
            model=EMBEDDING_MODEL,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        Settings.embed_model = embed_model

        client = chromadb.PersistentClient(path=self.db_path)
        vector_store = ChromaVectorStore(
            chroma_collection=client.get_or_create_collection(
                name="nccn_nsclc_v5",
                metadata={"hnsw:space": "cosine"},
            )
        )
        self.index = VectorStoreIndex.from_vector_store(vector_store)

    def retrieve(
        self,
        cancer_type: str,
        indication_category: str,
        query_text: str = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Retrieve NCCN criteria for a case.

        Args:
            cancer_type: e.g., "nsclc"
            indication_category: e.g., "staging", "initial_diagnosis", etc.
            query_text: Optional semantic query (e.g., patient summary). If not provided,
                        uses indication_category as the query.
            top_k: Number of criteria to return

        Returns:
            List of dicts with keys: passage_id, criterion_text, required_evidence, source
        """
        # Build query string
        if not query_text:
            query_text = f"NCCN criteria for {cancer_type} {indication_category}"

        # Retrieve from index with metadata filter
        retriever = self.index.as_retriever(
            similarity_top_k=top_k,
            filters=[
                {
                    "key": "cancer_type",
                    "value": cancer_type,
                },
                {
                    "key": "indication_category",
                    "value": indication_category,
                },
            ],
        )

        nodes = retriever.retrieve(query_text)

        # Format results
        results = []
        for node in nodes:
            results.append(
                {
                    "passage_id": node.metadata.get("passage_id"),
                    "criterion_text": node.text.split("\n\nRequired Evidence:")[0],  # Extract criterion portion
                    "required_evidence": node.metadata.get("required_evidence", []),
                    "source": node.metadata.get("reference", "NCCN"),
                    "score": node.score,  # Similarity score from vector search
                }
            )

        return results


# Singleton for phase 3b
_retriever_instance = None


def get_retriever() -> ChromaNcclnRetriever:
    """Get or initialize the Chroma NCCN retriever."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = ChromaNcclnRetriever()
    return _retriever_instance
