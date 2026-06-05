"""
Embedding service for RAG corpus (Phase 3b).

Uses OpenAI text-embedding-3-small (pinned snapshot for Determinism Contract invariant 11).
Caches embeddings to avoid redundant API calls.
"""

import hashlib
import json
import os
from typing import List

import openai


# Pinned embedding model (Determinism Contract invariant 11)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536  # text-embedding-3-small output dimension


def _hash_text(text: str) -> str:
    """SHA-256 hash of text for caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder:
    """Wrapper around OpenAI embeddings with caching."""

    def __init__(self, cache_file: str = None):
        """
        Args:
            cache_file: Optional path to JSON cache file for embeddings.
                        If provided, cache is loaded on init and updated on each embed call.
        """
        self.cache_file = cache_file
        self.cache = {}

        if cache_file and os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                self.cache = json.load(f)

    def embed(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dimensions for text-embedding-3-small)
        """
        text_hash = _hash_text(text)

        # Check cache
        if text_hash in self.cache:
            return self.cache[text_hash]

        # Call OpenAI API
        response = openai.Client().embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        embedding = response.data[0].embedding

        # Cache it
        self.cache[text_hash] = embedding
        if self.cache_file:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f)

        return embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts (more efficient than individual calls).

        Args:
            texts: List of text strings

        Returns:
            List of embedding vectors
        """
        # Check cache for all texts first
        embeddings = []
        texts_to_embed = []
        text_hashes = []

        for text in texts:
            text_hash = _hash_text(text)
            text_hashes.append(text_hash)
            if text_hash in self.cache:
                embeddings.append(self.cache[text_hash])
            else:
                texts_to_embed.append(text)

        # Batch embed uncached texts
        if texts_to_embed:
            response = openai.Client().embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts_to_embed,
            )
            new_embeddings = [item.embedding for item in response.data]

            # Cache and merge
            for text, embedding in zip(texts_to_embed, new_embeddings):
                text_hash = _hash_text(text)
                self.cache[text_hash] = embedding

            if self.cache_file:
                with open(self.cache_file, "w") as f:
                    json.dump(self.cache, f)

        # Return in original order
        result = []
        cached_idx = 0
        embed_idx = 0
        for text_hash in text_hashes:
            if text_hash in [_hash_text(t) for t in texts_to_embed]:
                result.append(self.cache[text_hash])
            else:
                result.append(embeddings[cached_idx])
                cached_idx += 1

        return result
