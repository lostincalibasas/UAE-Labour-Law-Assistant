# Phase 6 — FastAPI integration

Implemented on `feature/fastapi-backend`. No commits, pushes, merges or branch
switches were performed. No Docker or cloud changes are included.

## Delivered

- `backend/main.py`: lazy FastAPI app and safe validation/exception responses.
- `backend/routes.py`: `POST /api/v1/ask`, `GET /health/live`, `GET /health/ready`.
- `backend/schemas.py`: strict shared request and response contracts; malformed
  responses are withheld, and error text is resolved through the existing catalog.
- `backend/service.py`: guarded, serialized delegation to the existing generator.
  No duplicate retrieval, prompt, citation-resolution or legal-answer logic.
- `backend/__main__.py`: Windows Phase 3.5 locked snapshot launcher, independent
  worker, byte verification, shared Chroma guard and shutdown integrity record.
- `backend_client.py` and `app.py`: HTTP-based Streamlit integration, preserving
  answer/citation rendering and safe failures without importing the RAG pipeline.
- `rag_errors.py`: four additional frontend configuration/transport error codes.
- `requirements.txt`: FastAPI 0.162.4 added; all existing pins retained, including
  Uvicorn 0.54.0, Pydantic 2.13.5, Starlette 1.7.0 and HTTPX 0.28.1. The original
  requirements file encoding was retained.
- `README.md`: architecture, configuration, launch instructions, endpoint/status
  contracts, example payload/response and offline test commands.
- `tests/test_backend.py`: 24 new tests. Existing UI fixture targets in
  `tests/test_phase2.py` and `tests/test_phase3.py` now mock the HTTP boundary;
  their original rendering assertions remain intact.

## Validation

Final `python -B -m unittest discover -s tests -q`: **188 passed, 0 failed**
(164 existing + 24 new). Two legacy UI fixture failures on the initial full run
were resolved by updating their mock target from direct generation to the HTTP
client. No existing tests were removed or weakened.

Coverage includes strict invalid input rejection, response compatibility, exact
citations/excerpts, abstention, operational failures, safe error messages, missing
configuration, lazy imports, health endpoints, Streamlit → HTTP → FastAPI
integration, snapshot tampering, original-path refusal and temporary-source locks.
The HTTP integration uses an in-process transport and mocked pipeline; UI rendering
uses a mocked Streamlit interface, not a browser session.

`pip check`: no broken requirements. FastAPI installation did not upgrade existing
dependencies. `git diff --check`: passed (only existing newline-conversion notices).

Hashes match for all **36 protected artifacts**, all historical outputs and review
materials included in the baseline, and the unchanged generation, retrieval,
citation and experimental-selector source files: **85 baseline files checked,
0 changed**. See `runs/phase6-baseline-01.json` and
`runs/phase6-integrity-01.json`. Reports use new output paths.

No embeddings were rebuilt, no Chroma client opened the original index, and no
live DeepSeek generation or judge evaluation was executed. Launcher validation
used temporary fixture indexes and mocked server launch. Existing evaluation
behavior and the disabled experimental law selector are preserved.

## Compatibility and remaining limits

Streamlit now requires a separate backend process. Start it with
`python -B -m backend --port 8000`, then run `streamlit run app.py` in another
activated terminal. The launcher binds to loopback and uses a new isolated copy.
Starting plain Uvicorn without that guard intentionally leaves Ask/readiness
unavailable. The source must be quiescent for snapshot creation; copies and their
reports are retained. Existing direct Python pipeline callers are unchanged.

The new HTTP request contract caps questions at 4,000 characters and `top_k` at
50. HTTP 200 distinguishes `ok` from `insufficient_evidence` in the body;
operational failures use HTTP 503, validation failures 422, and an unexpected
adapter exception 500. All preserve the safe response shape.

Readiness is explicitly a **local configuration preflight**. It checks the guard,
dependency presence, copied file readability and local credential validation. It
does not verify DeepSeek authentication/network availability, load BGE, validate
cached weights, or inspect collection contents. Those remain first-request checks
in the existing pipeline. Citation identity still does not prove claim support.

The Windows launcher is single-worker with serialized Ask operations; it is not a
public deployment setup. There is no authentication or cancellation protocol.
A frontend timeout may leave backend work running; no automatic retries are used.
A real browser session and a live isolated RAG smoke test remain unverified and
must not be inferred from these mocked tests. Dockerization is a separate phase.
