"""Resolve index paths at use time and fail closed in isolated test workers."""

import os
from pathlib import Path

from rag_errors import RAGError

PROTECTED_INDEX = Path(__file__).resolve().parent / "data" / "chroma_db"


def disjoint(path, original=PROTECTED_INDEX):
    path, original = Path(path).resolve(), Path(original).resolve()
    return path != original and original not in path.parents and path not in original.parents


def resolve_index_path(default=PROTECTED_INDEX):
    selected = Path(os.environ.get("RAG_INDEX_PATH") or default).resolve()
    root = os.environ.get("RAG_TEST_INDEX_ROOT")
    if root:
        root = Path(root).resolve()
        if (not os.environ.get("RAG_INDEX_PATH") or not disjoint(root)
                or selected not in {root / "reference", root / "working"}
                or not disjoint(selected)):
            raise RAGError("index_isolation", "retrieval")
    return selected
