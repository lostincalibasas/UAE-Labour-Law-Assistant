"""Streamlit HTTP client. Never imports retrieval or generation."""

import os
from urllib.parse import urlsplit
import httpx
from backend.schemas import AskRequest, AskResponse
from rag_errors import RAGError, operational_failure


def ask_backend(question, top_k=10):
    try:
        payload = AskRequest(question=question, top_k=top_k).model_dump()
    except Exception:
        return operational_failure(RAGError("invalid_input", "ui"))
    try:
        base_url = os.environ.get("RAG_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Invalid API URL")
    except Exception:
        return operational_failure(RAGError("backend_configuration", "ui"))
    try:
        # Zero retries, redirects disabled, no environment proxy forwarding.
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0),
                          follow_redirects=False, trust_env=False) as client:
            response = client.post(base_url + "/api/v1/ask", json=payload)
        if response.status_code not in {200, 422, 500, 503}:
            raise ValueError("Unexpected backend status")
        result = AskResponse.model_validate(response.json())
        if (response.status_code == 200) == (result.status == "operational_error"):
            raise ValueError("Inconsistent HTTP outcome")
        return result.model_dump()
    except httpx.TimeoutException:
        return operational_failure(RAGError("backend_timeout", "ui"))
    except httpx.RequestError:
        return operational_failure(RAGError("backend_connection", "ui"))
    except Exception:
        return operational_failure(RAGError("backend_response_invalid", "ui"))
