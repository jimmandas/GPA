"""
Chroma-based NCCN retriever for Phase 3b RAG (LlamaIndex + Chroma).

Queries the NCCN corpus index by cancer type, indication, and semantic similarity.
Returns ranked passages for Policy Mapper to evaluate against patient evidence.
"""

import os
import pathlib
from typing import List, Dict

from llama_index.core import VectorStoreIndex, Settings, StorageContext
from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter, FilterOperator, FilterCondition
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb


CHROMA_DB_PATH = pathlib.Path(__file__).parent.parent / "chroma_db"
EMBEDDING_MODEL = "text-embedding-3-small"


class ChromaNcclnRetriever:
    """Retrieve from a Chroma vector store collection.

    Two roles (ADR-019 Path 2):
      - `retrieve()` — NCCN *criteria* (the authorization rules) from nccn_nsclc_v5,
        filtered by cancer_type + indication_category. The policy mapper checks the
        patient against these.
      - `retrieve_evidence()` — *clinical reference* passages from the real PDQ corpus
        (pdq_nsclc_v1), filtered by cancer_type only, ranked semantically. These GROUND
        the policy mapper's reasoning; they are evidence, NOT criteria to be marked
        met/unmet.
    """

    def __init__(self, db_path: str = None, collection_name: str = "nccn_nsclc_v5"):
        """
        Args:
            db_path: Path to Chroma persistent DB. Defaults to chroma_db/ in repo root.
            collection_name: Chroma collection to query (nccn_nsclc_v5 = criteria;
                             pdq_nsclc_v1 = PDQ clinical-evidence corpus).
        """
        self.db_path = db_path or str(CHROMA_DB_PATH)
        self.collection_name = collection_name

        # Load Chroma index
        embed_model = OpenAIEmbedding(
            model=EMBEDDING_MODEL,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        Settings.embed_model = embed_model

        client = chromadb.PersistentClient(path=self.db_path)
        vector_store = ChromaVectorStore(
            chroma_collection=client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self.index = VectorStoreIndex.from_vector_store(
            vector_store, storage_context=storage_context
        )

    def retrieve_evidence(
        self,
        cancer_type: str,
        query_text: str,
        top_k: int = 4,
    ) -> List[Dict]:
        """
        Retrieve clinical-reference passages (PDQ corpus) to ground policy-mapper
        reasoning. Semantic ranking, cancer_type filter only (PDQ chunks have no
        indication_category — they are prose organized by stage/topic, ADR-019).

        Returns:
            List of dicts: passage_id, section_heading, text, source, score.
        """
        filters = MetadataFilters(
            filters=[
                MetadataFilter(key="cancer_type", value=cancer_type, operator=FilterOperator.EQ),
            ],
            condition=FilterCondition.AND,
        )
        retriever = self.index.as_retriever(similarity_top_k=top_k, filters=filters)
        nodes = retriever.retrieve(query_text)
        return [
            {
                "passage_id": n.metadata.get("passage_id"),
                "section_heading": n.metadata.get("section_heading", ""),
                "text": n.text,
                "source": n.metadata.get("source", "NCI PDQ"),
                "score": n.score,
            }
            for n in nodes
        ]

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

        # Retrieve from index with metadata filters (MetadataFilters API, not raw list)
        filters = MetadataFilters(
            filters=[
                MetadataFilter(key="cancer_type", value=cancer_type, operator=FilterOperator.EQ),
                MetadataFilter(key="indication_category", value=indication_category, operator=FilterOperator.EQ),
            ],
            condition=FilterCondition.AND,
        )
        retriever = self.index.as_retriever(
            similarity_top_k=top_k,
            filters=filters,
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


# Singletons: criteria retriever (nccn_nsclc_v5) + PDQ evidence retriever (pdq_nsclc_v1)
_retriever_instance = None
_evidence_retriever_instance = None

PDQ_COLLECTION = "pdq_nsclc_v1"


def get_retriever() -> ChromaNcclnRetriever:
    """Criteria retriever — NCCN authorization rules (nccn_nsclc_v5)."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = ChromaNcclnRetriever()
    return _retriever_instance


def get_evidence_retriever() -> ChromaNcclnRetriever:
    """Clinical-evidence retriever — real PDQ corpus (pdq_nsclc_v1), ADR-019 Path 2."""
    global _evidence_retriever_instance
    if _evidence_retriever_instance is None:
        _evidence_retriever_instance = ChromaNcclnRetriever(collection_name=PDQ_COLLECTION)
    return _evidence_retriever_instance
