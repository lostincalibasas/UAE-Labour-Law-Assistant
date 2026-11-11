"""Shared HTTP contracts, usable by the frontend without importing the pipeline."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from evidence_citations import FALLBACK
from rag_errors import RAGError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A question is required")
        return value


class SafeError(StrictModel):
    code: str
    message: str
    retryable: bool

    @model_validator(mode="after")
    def catalog_message(self):
        # Never expose SDK messages or a remote server's arbitrary error text.
        error = RAGError(self.code, "generation")
        self.code, self.message, self.retryable = error.code, error.message, error.retryable
        return self


class Citation(StrictModel):
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    source_document: str = Field(min_length=1)
    article: str | None
    filename: str | None
    excerpt: str = Field(min_length=1)


class CitationValidation(StrictModel):
    status: Literal["valid", "no_evidence", "insufficient_evidence", "invalid_citations",
                    "missing_citations", "not_evaluated"]
    invalid_ids: list[str]
    invalid_markers: list[str]


class AskResponse(StrictModel):
    status: Literal["ok", "insufficient_evidence", "operational_error"]
    error: SafeError | None
    answer: str
    sources: list[str]
    citations: list[Citation]
    citation_validation: CitationValidation
    claim_support: Literal["not_evaluated"]

    @model_validator(mode="after")
    def consistent_outcome(self):
        validation = self.citation_validation
        if self.status == "operational_error":
            if (self.error is None or self.answer or self.sources or self.citations
                    or validation.status != "not_evaluated"
                    or validation.invalid_ids or validation.invalid_markers):
                raise ValueError("Inconsistent operational outcome")
        elif self.error is not None:
            raise ValueError("Unexpected error on legal outcome")
        elif self.status == "ok":
            if (not self.answer.strip() or not self.citations or not self.sources
                    or validation.status != "valid"
                    or validation.invalid_ids or validation.invalid_markers):
                raise ValueError("Inconsistent cited outcome")
        elif (self.answer != FALLBACK or self.sources or self.citations
              or validation.status in {"valid", "not_evaluated"}):
            raise ValueError("Inconsistent abstention")
        return self


class LiveResponse(StrictModel):
    status: Literal["alive"] = "alive"


class ReadyResponse(StrictModel):
    status: Literal["ready", "unavailable"]
    scope: Literal["local_configuration"] = "local_configuration"
    error: SafeError | None
