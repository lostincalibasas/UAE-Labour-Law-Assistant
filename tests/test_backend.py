"""Phase 6: offline HTTP integration, mocked providers and temporary indexes only."""

import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import create_app
from backend import service
from backend import __main__ as launcher
from backend.schemas import AskResponse
import backend_client
from evidence_citations import FALLBACK, build_evidence, resolve_answer
from index_isolation import tree_hashes
from index_paths import PROTECTED_INDEX
from rag_errors import ERRORS, RAGError, operational_failure

ROOT = Path(__file__).resolve().parents[1]
SECRET = "private-test-secret-not-for-output"
EVIDENCE = build_evidence([
    {"text": "Exact excerpt one.", "source_document": "Law A", "article": "Article 9", "filename": "a.pdf"},
    {"text": "Exact excerpt two.", "source_document": "Law B", "article": None, "filename": None},
])


def success():
    return resolve_answer("A claim [E1]. Another claim [E2].", EVIDENCE)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.http = self.enterContext(TestClient(create_app()))
        self.path = self.enterContext(patch.object(service, "isolated_path", return_value=Path("unused-copy")))
        self.generate = self.enterContext(patch("generate_answer.generate_answer", return_value=success()))

    def test_success_preserves_all_fields_and_calls_pipeline_once(self):
        result = self.http.post("/api/v1/ask", json={"question": "A question"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), success())
        self.generate.assert_called_once_with("A question", top_k=10)
        self.assertEqual(AskResponse.model_validate(result.json()).claim_support, "not_evaluated")

    def test_explicit_top_k_preserved(self):
        self.http.post("/api/v1/ask", json={"question": "test", "top_k": 5})
        self.generate.assert_called_once_with("test", top_k=5)

    def test_invalid_inputs_do_not_echo_content_or_invoke_pipeline(self):
        cases = [{}, {"question": None}, {"question": 123}, {"question": True},
                 {"question": []}, {"question": ""}, {"question": " \n\t"},
                 {"question": "a" * 4001}, {"question": SECRET, "unknown": SECRET}]
        cases += [{"question": SECRET, "top_k": value} for value in (0, -1, 51, True, 1.5, "10", None)]
        for case in cases:
            with self.subTest(case_type=str(type(case))), self.assertLogs("compliance_rag"):
                result = self.http.post("/api/v1/ask", json=case)
            self.assertEqual(result.status_code, 422)
            self.assertEqual(result.json()["error"]["code"], "invalid_input")
            self.assertNotIn(SECRET, result.text)
        self.generate.assert_not_called()
        self.path.assert_not_called()

    def test_malformed_json_returns_safe_validation_error(self):
        with self.assertLogs("compliance_rag"):
            result = self.http.post("/api/v1/ask", content='{"question": "' + SECRET,
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(SECRET, result.text)
        self.generate.assert_not_called()

    def test_insufficient_evidence_and_rejected_citations_remain_distinct(self):
        for text, evidence, validation in [
            (FALLBACK, EVIDENCE, "insufficient_evidence"), ("", [], "no_evidence"),
            ("A claim [E99].", EVIDENCE, "invalid_citations"),
            ("No citation", EVIDENCE, "missing_citations"),
        ]:
            self.generate.return_value = resolve_answer(text, evidence)
            result = self.http.post("/api/v1/ask", json={"question": "test"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), self.generate.return_value)
            self.assertEqual(result.json()["citation_validation"]["status"], validation)

    def test_operational_failures_use_safe_503_response(self):
        for code in ("api_timeout", "api_authentication", "retrieval_unavailable", "configuration_missing"):
            with self.assertLogs("compliance_rag"):
                result = operational_failure(RAGError(code, "generation"))
            result["error"]["message"] = SECRET
            self.generate.return_value = result
            response = self.http.post("/api/v1/ask", json={"question": "test"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["message"], ERRORS[code][0])
            self.assertEqual(response.json()["answer"], "")
            self.assertNotIn(SECRET, response.text)

    def test_unexpected_and_malformed_pipeline_results_are_withheld(self):
        bad = success()
        bad["citations"] = []
        for response in ({}, bad, None):
            self.generate.return_value = response
            with self.assertLogs("compliance_rag"):
                result = self.http.post("/api/v1/ask", json={"question": "test"})
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json()["answer"], "")
        self.generate.side_effect = RuntimeError(SECRET)
        with self.assertLogs("compliance_rag") as logs:
            result = self.http.post("/api/v1/ask", json={"question": "test"})
        self.assertNotIn(SECRET, result.text + str(logs.output))

    def test_no_isolation_means_no_generation(self):
        self.path.side_effect = RAGError("index_isolation", "retrieval")
        with self.assertLogs("compliance_rag"):
            result = self.http.post("/api/v1/ask", json={"question": "test"})
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["error"]["code"], "index_isolation")
        self.generate.assert_not_called()

    def test_openapi_documents_response_and_validation_contract(self):
        schema = self.http.get("/openapi.json").json()
        self.assertEqual(set(schema["paths"]), {"/api/v1/ask", "/health/live", "/health/ready"})
        responses = schema["paths"]["/api/v1/ask"]["post"]["responses"]
        self.assertEqual(responses["422"]["content"]["application/json"]["schema"]["$ref"],
                         "#/components/schemas/AskResponse")
        self.generate.assert_not_called()


class HealthAndIsolationTests(unittest.TestCase):
    def test_fresh_import_liveness_and_frontend_never_load_rag_dependencies(self):
        script = '''
import sys, os
from unittest.mock import MagicMock, patch
for name in ('chromadb', 'sentence_transformers', 'openai', 'dotenv'):
    sys.modules[name] = None
from fastapi.testclient import TestClient
from backend.main import app
import backend_client
with TestClient(app) as client:
    assert client.get('/health/live').json() == {'status': 'alive'}
    assert client.get('/health/ready').status_code == 503
assert 'generate_answer' not in sys.modules
assert 'retrieve_bge' not in sys.modules
st = MagicMock()
st.button.return_value = False
with patch.dict(sys.modules, {'streamlit': st}):
    import app
assert 'generate_answer' not in sys.modules
assert 'retrieve_bge' not in sys.modules
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_readiness_checks_only_copy_and_client_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "chroma.sqlite3").write_bytes(b"temporary fixture")
            before = tree_hashes(path)
            with patch.object(service, "isolated_path", return_value=path), \
                 patch.object(service.importlib.util, "find_spec", return_value=object()), \
                 patch("generate_answer.get_api_client") as client, \
                 patch("retrieve_bge.get_model") as model, \
                 patch("retrieve_bge.get_collection") as collection, TestClient(create_app()) as http:
                response = http.get("/health/ready")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["scope"], "local_configuration")
                client.return_value.__enter__.assert_called_once()
                client.return_value.chat.completions.create.assert_not_called()
                model.assert_not_called()
                collection.assert_not_called()
            self.assertEqual(tree_hashes(path), before)

    def test_readiness_missing_or_invalid_config_is_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "chroma.sqlite3").write_bytes(b"fixture")
            with patch.object(service, "isolated_path", return_value=path), \
                 patch.object(service.importlib.util, "find_spec", return_value=object()), \
                 patch("dotenv.load_dotenv"), patch("openai.OpenAI") as sdk, \
                 TestClient(create_app()) as http:
                for key in ("", "changeme", "secret with spaces"):
                    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": key}):
                        response = http.get("/health/ready")
                    self.assertEqual(response.status_code, 503)
                    self.assertIn(response.json()["error"]["code"],
                                  {"configuration_missing", "configuration_invalid"})
                sdk.assert_not_called()

    def test_readiness_missing_dependency_or_file(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(service, "isolated_path", return_value=Path(temp)), \
             patch.object(service.importlib.util, "find_spec") as find, \
             patch("generate_answer.get_api_client") as sdk:
            find.return_value = None
            self.assertEqual(service.readiness().error.code, "dependency_unavailable")
            find.return_value = object()
            self.assertEqual(service.readiness().error.code, "index_missing")
            sdk.assert_not_called()

    def test_original_path_refused_before_any_file_open(self):
        with patch.object(service, "require_isolated_index"), \
             patch.object(service, "resolve_index_path", return_value=PROTECTED_INDEX), \
             patch.object(Path, "open") as file:
            self.assertEqual(service.readiness().error.code, "index_isolation")
            file.assert_not_called()

    def test_unguarded_app_refuses_original_and_has_live_endpoint(self):
        with patch("index_isolation._guarded_path", None), TestClient(create_app()) as http:
            self.assertEqual(http.get("/health/live").status_code, 200)
            self.assertEqual(http.get("/health/ready").json()["error"]["code"], "index_isolation")
            with self.assertLogs("compliance_rag"):
                result = http.post("/api/v1/ask", json={"question": "test"})
            self.assertEqual(result.json()["error"]["code"], "index_isolation")

    @unittest.skipUnless(os.name == "nt", "Uses existing Windows snapshot locks")
    def test_launcher_locks_and_copies_temporary_source_retains_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            source, workspace = Path(temp) / "source", Path(temp) / "workspace"
            source.mkdir()
            workspace.mkdir()
            (source / "chroma.sqlite3").write_bytes(b"fixture")
            before = tree_hashes(source)
            def child_factory(*args, **kwargs):
                with self.assertRaises(OSError):
                    (source / "chroma.sqlite3").write_bytes(b"must not change")
                return Mock(wait=Mock(return_value=0))
            with patch.object(launcher, "PROTECTED_INDEX", source), \
                 patch.object(launcher.tempfile, "mkdtemp", return_value=str(workspace)), \
                 patch.object(launcher.subprocess, "Popen", side_effect=child_factory):
                self.assertEqual(launcher.launch(8000), 0)
            self.assertEqual(tree_hashes(source), before)
            self.assertEqual(tree_hashes(workspace / "working"), before)
            self.assertTrue(json.loads((workspace / "shutdown-integrity.json").read_text())
                            ["original_hashes_unchanged"])

    def test_worker_verifies_copy_before_installing_guard_and_serving(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ):
            root = Path(temp)
            target = root / "working"
            target.mkdir()
            (target / "chroma.sqlite3").write_bytes(b"fixture")
            (root / "source-baseline.json").write_text(json.dumps({
                "source": str(PROTECTED_INDEX), "hashes": tree_hashes(target)}))
            with patch.object(launcher, "install_chroma_guard") as guard, patch("uvicorn.run") as serve:
                launcher.serve_copy(root, 8000)
                guard.assert_called_once_with(target)
                self.assertEqual(os.environ["RAG_INDEX_PATH"], str(target))
                self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
                (target / "chroma.sqlite3").write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    launcher.serve_copy(root, 8000)
                self.assertEqual(guard.call_count, 1)
                self.assertEqual(serve.call_count, 1)

    def test_unsafe_temporary_base_is_refused_before_creating_any_files(self):
        with patch.object(launcher.tempfile, "gettempdir", return_value=str(PROTECTED_INDEX)), \
             patch.object(launcher.tempfile, "mkdtemp") as create, \
             patch.object(launcher, "locked_snapshot") as snapshot:
            with self.assertRaises(ValueError):
                launcher.launch(8000)
            create.assert_not_called()
            snapshot.assert_not_called()


class FrontendTests(unittest.TestCase):
    def http_client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_http_frontend_preserves_response_and_configurable_url(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=success())
        client = self.http_client(handler)
        with patch.object(backend_client.httpx, "Client", return_value=client), \
             patch.dict(os.environ, {"RAG_API_BASE_URL": "http://localhost:9000/"}):
            self.assertEqual(backend_client.ask_backend("test"), success())
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), "http://localhost:9000/api/v1/ask")
        self.assertEqual(json.loads(requests[0].content), {"question": "test", "top_k": 10})

    def test_backend_connection_timeout_and_malformed_responses(self):
        for error, code in [(httpx.ConnectError(SECRET), "backend_connection"),
                            (httpx.ReadTimeout(SECRET), "backend_timeout")]:
            with patch.object(backend_client.httpx, "Client") as client, self.assertLogs("compliance_rag") as logs:
                client.return_value.__enter__.return_value.post.side_effect = error
                result = backend_client.ask_backend("test")
                self.assertEqual(result["error"]["code"], code)
                self.assertNotIn(SECRET, json.dumps(result) + str(logs.output))
                client.return_value.__enter__.return_value.post.assert_called_once()
        for response in (httpx.Response(200, text=SECRET), httpx.Response(200, json={}),
                         httpx.Response(500, text=SECRET), httpx.Response(302),
                         httpx.Response(503, json=success())):
            client = self.http_client(lambda request: response)
            with patch.object(backend_client.httpx, "Client", return_value=client), self.assertLogs("compliance_rag"):
                result = backend_client.ask_backend("test")
            self.assertEqual(result["error"]["code"], "backend_response_invalid")

    def test_bad_url_and_question_never_make_http_requests(self):
        with patch.object(backend_client.httpx, "Client") as client:
            for url in ("", "ftp://localhost", "http://user:secret@localhost", "http://localhost?secret=yes"):
                with patch.dict(os.environ, {"RAG_API_BASE_URL": url}), self.assertLogs("compliance_rag"):
                    self.assertEqual(backend_client.ask_backend("test")["error"]["code"], "backend_configuration")
            with self.assertLogs("compliance_rag"):
                self.assertEqual(backend_client.ask_backend(" ")["error"]["code"], "invalid_input")
            client.assert_not_called()

    def test_streamlit_through_http_to_api_displays_exact_citations(self):
        st = MagicMock()
        st.button.return_value = True
        st.text_input.return_value = "test"
        with TestClient(create_app()) as api, \
             patch.object(service, "isolated_path"), \
             patch("generate_answer.generate_answer", return_value=success()) as generate:
            client = self.http_client(lambda request: httpx.Response(
                200, json=api.post("/api/v1/ask", json=json.loads(request.content)).json()))
            with patch.object(backend_client.httpx, "Client", return_value=client), \
                 patch.dict(sys.modules, {"streamlit": st}):
                runpy.run_path(str(ROOT / "app.py"), run_name="_phase6_app")
        generate.assert_called_once()
        st.write.assert_called_once_with(success()["answer"])
        self.assertEqual(st.expander.call_count, 2)
        st.text.assert_any_call("Exact excerpt one.")
        st.text.assert_any_call("Exact excerpt two.")
        st.error.assert_not_called()

    def test_frontend_error_objects_are_sanitized_and_abstention_preserved(self):
        with self.assertLogs("compliance_rag"):
            error = operational_failure(RAGError("api_timeout", "generation"))
        error["error"]["message"] = SECRET
        for status, body in [(503, error), (200, resolve_answer(FALLBACK, EVIDENCE))]:
            client = self.http_client(lambda request: httpx.Response(status, json=body))
            with patch.object(backend_client.httpx, "Client", return_value=client):
                result = backend_client.ask_backend("test")
            self.assertEqual(result["status"], body["status"])
            self.assertNotIn(SECRET, json.dumps(result))

    def test_inconsistent_or_semantically_verified_claim_is_not_accepted(self):
        for field, value in [("claim_support", "verified"), ("status", "unknown"),
                             ("error", {"code": "api_timeout", "message": SECRET, "retryable": True}),
                             ("citations", [])]:
            result = copy.deepcopy(success())
            result[field] = value
            with self.assertRaises(ValidationError):
                AskResponse.model_validate(result)


if __name__ == "__main__":
    unittest.main()
