"""Versioned application routes and lightweight health endpoints."""

from fastapi import APIRouter, Response
from backend import service
from backend.schemas import AskRequest, AskResponse, LiveResponse, ReadyResponse

router = APIRouter()


@router.post("/api/v1/ask", response_model=AskResponse,
             responses={422: {"model": AskResponse}, 500: {"model": AskResponse},
                        503: {"model": AskResponse}})
def ask(request: AskRequest, response: Response):
    result = service.ask(request.question, request.top_k)
    if result.status == "operational_error":
        response.status_code = 503
    return result


@router.get("/health/live", response_model=LiveResponse)
def live():
    return LiveResponse()


@router.get("/health/ready", response_model=ReadyResponse,
            responses={503: {"model": ReadyResponse}})
def ready(response: Response):
    result = service.readiness()
    if result.status != "ready":
        response.status_code = 503
    return result
