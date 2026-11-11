"""Verify a consistent index snapshot and run BGE retrieval on copies only.

No API calls, embeddings rebuilds, source Chroma clients, or source repairs.
Temporary copies/reports are retained for inspection; nothing is overwritten.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from artifact_io import require_new_output, write_new_json
from index_paths import PROTECTED_INDEX, disjoint, resolve_index_path
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_integrity import index_fingerprint, logical_differences

QUESTION = "How much notice must an employee give when resigning under the general UAE employment law?"


def worker(root, kind):
    root = root.resolve()
    target = root / kind
    if not disjoint(root) or kind not in {"reference", "working"}:
        raise ValueError("Worker requires a separate snapshot workspace")
    manifest = json.loads((root / "source-baseline.json").read_text(encoding="utf-8"))
    if not disjoint(root, manifest["source"]) or tree_hashes(target) != manifest["hashes"]:
        raise ValueError("Worker requires a byte-verified complete copy")
    os.environ["RAG_TEST_INDEX_ROOT"] = str(root)
    os.environ["RAG_INDEX_PATH"] = str(target)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    assert resolve_index_path() == target
    opened = install_chroma_guard(target)
    import chromadb
    from chromadb.config import Settings
    settings = Settings(migrations="validate", anonymized_telemetry=False)
    report = {"copy": kind, "index_path": str(target), "api_requests": 0}
    with chromadb.PersistentClient(path=str(target), settings=settings) as client:
        report["before"] = index_fingerprint(client)
    if kind == "working":
        import retrieve_bge
        # Generation and evaluation import this same BGE function; its path is
        # resolved at call time, not captured from the original module constant.
        import generate_answer
        import evaluate
        assert generate_answer.retrieve_chunks is retrieve_bge.retrieve_chunks
        started = time.perf_counter()
        try:
            chunks = evaluate.retrieve_chunks(QUESTION, top_k=5)
            report["retrieval"] = {
                "status": "ok", "question": QUESTION,
                "seconds": round(time.perf_counter() - started, 3),
                "count": len(chunks),
                "sources": [{"source_document": c["source_document"], "article": c["article"],
                             "distance": c["distance"]} for c in chunks],
            }
        except Exception as exc:
            from rag_errors import RAGError
            report["retrieval"] = {"status": "blocked",
                                   "code": exc.code if isinstance(exc, RAGError) else type(exc).__name__}
        finally:
            if retrieve_bge.client is not None:
                retrieve_bge.client.close()
                retrieve_bge.client = None
                retrieve_bge.client_path = None
    # Reopening after close tests logical stability across native flushes too.
    with chromadb.PersistentClient(path=str(target), settings=settings) as client:
        report["after"] = index_fingerprint(client)
    report["differences_after_reopen"] = logical_differences(report["before"], report["after"])
    report["opened_paths"] = sorted(set(opened))
    report["physical_copy_hashes_after"] = tree_hashes(target)
    write_new_json(root / f"{kind}-logical.json", report)


def verify(source, output=None):
    source = Path(source).absolute()
    if output:
        require_new_output(output)
        if not disjoint(output, source) or not disjoint(output):
            raise ValueError("Report path must be outside protected index storage")
    temporary_base = Path(tempfile.gettempdir()).resolve()
    if not disjoint(temporary_base, source) or not disjoint(temporary_base):
        raise ValueError("Temporary storage overlaps a protected index")
    root = Path(tempfile.mkdtemp(prefix="compliance-rag-index-", dir=temporary_base))
    report_path = Path(output) if output else root / "report.json"
    report = {"source": str(source), "workspace": str(root), "api_requests": 0, "status": "blocked"}
    print(f"Snapshot workspace: {root}", flush=True)
    try:
        with locked_snapshot(source) as snapshot:
            before = snapshot.hashes()
            write_new_json(root / "source-baseline.json",
                           {"source": str(source), "hashes": before, "directories": snapshot.directories})
            try:
                for kind in ("reference", "working"):
                    snapshot.copy_to(root / kind)
                report["snapshot_byte_match"] = True
                report["source_file_count"] = len(before)
                # Hold source locks until both workers finish; the originals
                # cannot be opened for write even if a worker guard regresses.
                for kind in ("reference", "working"):
                    print(f"Checking {kind} copy in a fresh process...", flush=True)
                    process = subprocess.run(
                        [sys.executable, "-B", str(Path(__file__).resolve()),
                         "--worker", kind, "--workspace", str(root)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    )
                    if process.returncode:
                        report["blocker"] = f"{kind} worker failed; see {kind}-failure.json if present"
                        break
                else:
                    reference = json.loads((root / "reference-logical.json").read_text(encoding="utf-8"))
                    working = json.loads((root / "working-logical.json").read_text(encoding="utf-8"))
                    report["copy_logical_differences"] = logical_differences(reference["before"], working["before"])
                    report["reference_after_reopen_differences"] = reference["differences_after_reopen"]
                    report["working_after_reopen_differences"] = working["differences_after_reopen"]
                    report["retrieval"] = working["retrieval"]
                    report["collections"] = {
                        name: {k: v for k, v in item.items() if k != "records"}
                        for name, item in reference["before"].items()
                    }
                    report["opened_paths"] = reference["opened_paths"] + working["opened_paths"]
                    report["status"] = "passed" if (
                        not report["copy_logical_differences"]
                        and not reference["differences_after_reopen"]
                        and not working["differences_after_reopen"]
                        and working["retrieval"]["status"] == "ok"
                    ) else "failed_or_blocked"
            finally:
                report["original_hashes_unchanged"] = snapshot.hashes() == before
                if not report["original_hashes_unchanged"]:
                    report["status"] = "failed"
    except Exception as exc:
        report["status"] = "blocked"
        report["blocker"] = f"{type(exc).__name__}: {exc}"
    write_new_json(report_path, report)
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
    print(f"Report: {report_path}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROTECTED_INDEX)
    parser.add_argument("--output", type=Path, help="New report file (default: temporary workspace/report.json)")
    parser.add_argument("--worker", choices=("reference", "working"), help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            if args.workspace is None:
                raise ValueError("Missing snapshot workspace")
            worker(args.workspace, args.worker)
        except Exception as exc:
            # Diagnostics contain no prompts, credentials, passage text or vectors.
            if args.workspace and disjoint(args.workspace):
                write_new_json(args.workspace / f"{args.worker}-failure.json",
                               {"type": type(exc).__name__, "message": str(exc)})
            raise SystemExit(2)
    else:
        result = verify(args.source, args.output)
        raise SystemExit(0 if result["status"] == "passed" else 2)


if __name__ == "__main__":
    main()
