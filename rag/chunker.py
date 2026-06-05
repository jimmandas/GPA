"""
Text chunker for NCCN guideline passages (Phase 3b).

Splits guideline text into fixed-size chunks with overlap for semantic continuity.
Each chunk is paired with metadata (source, passage_id, indication category) for retrieval.
"""

from typing import List, Dict
import re


class GuidanceChunk:
    """A single chunk of clinical guidance."""

    def __init__(
        self,
        text: str,
        passage_id: str,
        source: str,
        indication_category: str,
        cancer_type: str,
        chunk_index: int,
    ):
        """
        Args:
            text: The chunk text
            passage_id: Unique ID (e.g., "NCCN-NSCLC-STAG-1")
            source: Source document (e.g., "NCCN NSCLC v5.2026")
            indication_category: One of: initial_diagnosis, staging, post_treatment_surveillance, treatment_response
            cancer_type: Cancer type (e.g., "nsclc", "breast")
            chunk_index: Position in the larger passage (0, 1, 2, ...)
        """
        self.text = text
        self.passage_id = passage_id
        self.source = source
        self.indication_category = indication_category
        self.cancer_type = cancer_type
        self.chunk_index = chunk_index

    def to_dict(self) -> Dict:
        """Serialize to dict for storage/retrieval."""
        return {
            "passage_id": self.passage_id,
            "source": self.source,
            "indication_category": self.indication_category,
            "cancer_type": self.cancer_type,
            "chunk_index": self.chunk_index,
            "text": self.text,
        }


class Chunker:
    """Chunks guideline text into fixed-size passages with metadata."""

    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        """
        Args:
            chunk_size: Target chunk size in characters
            overlap: Overlap between consecutive chunks (for semantic continuity)
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(
        self,
        text: str,
        passage_id: str,
        source: str,
        indication_category: str,
        cancer_type: str,
    ) -> List[GuidanceChunk]:
        """
        Split a passage into chunks.

        Args:
            text: The full passage text
            passage_id: Unique ID for the passage
            source: Source document
            indication_category: Indication category
            cancer_type: Cancer type

        Returns:
            List of GuidanceChunk objects
        """
        # Clean text
        text = text.strip()
        if not text:
            return []

        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', text)  # Split on sentence boundaries

        current_chunk = ""
        chunk_index = 0

        for sentence in sentences:
            if len(current_chunk) + len(sentence) > self.chunk_size:
                # Chunk is full, save it
                if current_chunk.strip():
                    chunks.append(
                        GuidanceChunk(
                            text=current_chunk.strip(),
                            passage_id=passage_id,
                            source=source,
                            indication_category=indication_category,
                            cancer_type=cancer_type,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1

                # Start new chunk with overlap from previous
                # Take last N characters of previous chunk to maintain context
                if self.overlap > 0 and current_chunk:
                    current_chunk = current_chunk[-self.overlap:] + " " + sentence
                else:
                    current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        # Save final chunk
        if current_chunk.strip():
            chunks.append(
                GuidanceChunk(
                    text=current_chunk.strip(),
                    passage_id=passage_id,
                    source=source,
                    indication_category=indication_category,
                    cancer_type=cancer_type,
                    chunk_index=chunk_index,
                )
            )

        return chunks
