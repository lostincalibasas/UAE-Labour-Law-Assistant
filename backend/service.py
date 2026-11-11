"""Lazy orchestration only: retrieval, generation and citations stay in existing code."""

import importlib.util
from threading import Lock
from backend.schemas import AskResponse, ReadyResponse
from index_isolation import require_isolated_index
from index_paths import disjoint, resolve_index_path
from rag_errors import RAGError, operational_failure

# The retriever caches model/client globals. Serialize this local adapter's calls
# so first-use initialization cannot race. Run a single backend worker.
_pipeline_lock = Lock()


def isolated_path():
    require_isolated_index()
    path = resolve_index_path()
    if not disjoint(path):
        raise RAGError("index_isolation", "retrieval")
    return path


def ask(question, top_k=10):
    try:
        with _pipeline_lock:
            isolated_path()
            from generate_answer import generate_answer
            result = generate_answer(question, top_k=top_k)
        return AskResponse.model_validate(result)
    except RAGError as exc:
        return AskResponse.model_validate(operational_failure(exc))
    except Exception:
        return AskResponse.model_validate(operational_failure(RAGError("internal_error", "generation")))


def readiness():
    """Local preflight, not proof of remote access, model validity or legal coverage."""
    try:
        path = isolated_path()
        for dependency in ("chromadb", "sentence_transformers", "openai", "dotenv"):
            if importlib.util.find_spec(dependency) is None:
                raise RAGError("dependency_unavailable", "configuration")
        # No SQLite/Chroma client; only check readability of the guarded copy.
        try:
            with (path / "chroma.sqlite3").open("rb") as storage:
                if not storage.read(1):
                    raise RAGError("index_missing", "retrieval")
        except OSError:
            raise RAGError("index_missing", "retrieval") from None
        from generate_answer import get_api_client
        # Reuse credential validation; construction/close send no requests.
        with get_api_client():
            pass
        return ReadyResponse(status="ready", error=None)
    except RAGError as exc:
        error = exc
    except Exception:
        error = RAGError("internal_error", "configuration")
    return ReadyResponse(status="unavailable", error={
        "code": error.code, "message": error.message, "retryable": error.retryable,
    })
