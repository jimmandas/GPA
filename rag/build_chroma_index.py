"""
rag/build_chroma_index.py — one-time indexer for the NCCN corpus.

Reads every YAML fixture under policy/nccn_fixtures/, splits into per-criterion
documents, embeds them with Chroma's default model (sentence-transformers/
all-MiniLM-L6-v2), and writes a persistent Chroma collection to .chroma/.

Idempotent: nukes and rebuilds the collection each run so the index always
reflects the current corpus exactly.

Usage:
    PYTHONPATH=. python rag/build_chroma_index.py

After running, update config/rag_index.yaml:
  - set retriever_kind: "chroma"
  - set embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
  - set corpus_hash: <printed at the end of this script>

See ADR-011 (architecture), ADR-012 (embedding pinning), ADR-013 (corpus policy).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import yaml


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "policy" / "nccn_fixtures"
_CHROMA_PATH = _REPO_ROOT / ".chroma"
_COLLECTION_NAME = "nccn_criteria"
_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _criterion_documents(fixture_file: pathlib.Path) -> list[dict]:
    """Split one NCCN YAML fixture into per-criterion documents for indexing."""
    data = yaml.safe_load(fixture_file.read_text(encoding="utf-8"))
    indication = data.get("indication_category", "")
    modality = data.get("modality", "")
    overall_ref = data.get("overall_policy_reference", "")

    docs = []
    for criterion in data.get("criteria", []):
        passage_id = criterion.get("passage_id", "")
        criterion_text = criterion.get("criterion_text", "").strip()
        required_evidence = criterion.get("required_evidence", []) or []
        docs.append({
            "id": f"{indication}::{modality}::{passage_id}",
            "document": criterion_text,
            "metadata": {
                "indication_category": indication,
                "modality": modality,
                "passage_id": passage_id,
                "overall_policy_reference": overall_ref,
                "required_evidence_json": json.dumps(required_evidence, ensure_ascii=False),
                "source_fixture": fixture_file.name,
            },
        })
    return docs


def _build() -> str:
    """Build the Chroma collection. Returns the new corpus content hash."""
    import chromadb
    from chromadb.config import Settings

    print(f"Building Chroma index from {_FIXTURES_DIR}")
    print(f"  Embedding model: {_EMBEDDING_MODEL}")
    print(f"  Persist path:    {_CHROMA_PATH}")
    print()

    # Collect all criterion documents
    fixtures = sorted(_FIXTURES_DIR.glob("*.yaml"))
    if not fixtures:
        print(f"ERROR: no YAML fixtures found in {_FIXTURES_DIR}", file=sys.stderr)
        sys.exit(1)

    all_docs: list[dict] = []
    for fixture in fixtures:
        docs = _criterion_documents(fixture)
        print(f"  {fixture.name}: {len(docs)} criteria")
        all_docs.extend(docs)
    print(f"  TOTAL: {len(all_docs)} criterion documents to index\n")

    # Persistent client; nuke and rebuild the collection
    client = chromadb.PersistentClient(
        path=str(_CHROMA_PATH),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(name=_COLLECTION_NAME)
        print(f"  (dropped existing collection '{_COLLECTION_NAME}')")
    except Exception:
        pass  # not present yet

    collection = client.create_collection(name=_COLLECTION_NAME)

    collection.add(
        ids=[d["id"] for d in all_docs],
        documents=[d["document"] for d in all_docs],
        metadatas=[d["metadata"] for d in all_docs],
    )

    print(f"\n✓ Indexed {collection.count()} documents into '{_COLLECTION_NAME}'")

    # Compute the corpus content hash over the canonical document set.
    # This is what config/rag_index.yaml needs to record.
    canonical = json.dumps(
        sorted([
            {"id": d["id"], "document": d["document"], "metadata": d["metadata"]}
            for d in all_docs
        ], key=lambda r: r["id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    corpus_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    print("\n--- For config/rag_index.yaml ---")
    print(f"  retriever_kind:  chroma")
    print(f"  embedding_model: {_EMBEDDING_MODEL}")
    print(f"  corpus_hash:     {corpus_hash}")
    print(f"  corpus_path:     .chroma  (or keep policy/nccn_fixtures and adjust validator)")
    print()
    return corpus_hash


if __name__ == "__main__":
    _build()
