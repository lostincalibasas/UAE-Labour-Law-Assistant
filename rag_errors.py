"""Safe application errors and minimal operational logging.

Only allowlisted codes/messages reach callers or logs. Never include exception
text, request content, passages, credentials, or provider response bodies.
"""

import json
import logging

LOGGER = logging.getLogger("compliance_rag")

# code: (user-facing action, whether trying again may help)
ERRORS = {
    "index_isolation": ("Index isolation refused this storage path or a previously initialized client. Start a fresh isolated verification process.", False),
    "configuration_missing": ("Set DEEPSEEK_API_KEY in the project's .env file or environment, then try again.", False),
    "configuration_invalid": ("Check DEEPSEEK_API_KEY: replace placeholder values and remove whitespace, then try again.", False),
    "api_authentication": ("DeepSeek rejected the credentials or access. Check the API key and account permissions.", False),
    "api_connection": ("Could not connect to DeepSeek. Check the network connection and try again.", True),
    "api_timeout": ("DeepSeek did not respond in time. Please try again shortly.", True),
    "api_rate_limit": ("DeepSeek is limiting requests. Wait before trying again; check account limits if this continues.", True),
    "api_server": ("DeepSeek is temporarily unavailable. Please try again later.", True),
    "api_request": ("DeepSeek could not process the request. Try a shorter question; check the model and account configuration if this continues.", False),
    "api_response_invalid": ("DeepSeek returned an unusable response. No answer was shown. Please try again.", True),
    "api_response_empty": ("DeepSeek returned an empty answer. Please try again.", True),
    "api_response_truncated": ("DeepSeek's answer was cut off and has been withheld. Try a more focused question.", True),
    "index_missing": ("The local document index is missing. Restore the existing data/chroma_db directory before trying again.", False),
    "collection_missing": ("The compliance_bge collection is missing. Restore the correct existing index before trying again.", False),
    "collection_empty": ("The compliance_bge collection is empty. Restore a populated index before trying again.", False),
    "retrieval_unavailable": ("The document index could not be read. Check its availability and file permissions, then try again.", True),
    "retrieval_invalid": ("The document index returned unusable passages. Check the index and its source metadata.", False),
    "embedding_unavailable": ("The BGE embedding model could not be loaded or used. Check the model files and environment, then try again.", True),
    "dependency_unavailable": ("A required Python dependency is unavailable. Check the virtual environment and requirements.txt.", False),
    "invalid_input": ("Enter a non-empty question and use a positive integer for top_k.", False),
    "internal_error": ("The request could not be completed. Please try again; contact the app maintainer if this continues.", True),
}


class RAGError(Exception):
    def __init__(self, code, stage):
        self.code = code if code in ERRORS else "internal_error"
        self.stage = stage if stage in {"configuration", "retrieval", "generation", "response", "ui", "evaluation"} else "generation"
        self.message, self.retryable = ERRORS[self.code]
        super().__init__(self.message)


def operational_failure(error):
    if not isinstance(error, RAGError):
        error = RAGError("internal_error", "generation")
    LOGGER.warning(json.dumps({
        "event": "rag_operational_failure", "stage": error.stage,
        "code": error.code, "retryable": error.retryable,
    }))
    return {
        "status": "operational_error",
        "answer": "",
        "sources": [],
        "citations": [],
        "citation_validation": {"status": "not_evaluated", "invalid_ids": [], "invalid_markers": []},
        "claim_support": "not_evaluated",
        "error": {"code": error.code, "message": error.message, "retryable": error.retryable},
    }
