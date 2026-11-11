"""ASGI app. Import/startup performs no retrieval, model loading or API calls."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.routes import router
from rag_errors import RAGError, operational_failure


def create_app():
    application = FastAPI(title="UAE Labour Law RAG API", version="1.0.0")
    application.include_router(router)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Default validation errors echo submitted values; omit them entirely.
        return JSONResponse(status_code=422, content=operational_failure(
            RAGError("invalid_input", "generation")))

    @application.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse(status_code=500, content=operational_failure(
            RAGError("internal_error", "generation")))

    return application


app = create_app()
