"""Run one local API worker against a fresh Phase 3.5 snapshot, never the source."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from artifact_io import write_new_json
from index_isolation import install_chroma_guard, locked_snapshot, tree_hashes
from index_paths import PROTECTED_INDEX, disjoint


def serve_copy(workspace, port):
    workspace = Path(workspace).resolve()
    target = workspace / "working"
    if not disjoint(workspace):
        raise ValueError("Invalid snapshot workspace")
    manifest = json.loads((workspace / "source-baseline.json").read_text(encoding="utf-8"))
    if (not disjoint(workspace, manifest["source"])
            or tree_hashes(target) != manifest["hashes"]):
        raise ValueError("Snapshot verification failed")
    os.environ["RAG_TEST_INDEX_ROOT"] = str(workspace)
    os.environ["RAG_INDEX_PATH"] = str(target)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    install_chroma_guard(target)
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port,
                workers=1, access_log=False)


def launch(port):
    temporary_base = Path(tempfile.gettempdir()).resolve()
    if not disjoint(temporary_base):
        raise ValueError("Invalid temporary location")
    workspace = Path(tempfile.mkdtemp(prefix="compliance-rag-api-", dir=temporary_base))
    if not disjoint(workspace):
        raise ValueError("Invalid temporary location")
    with locked_snapshot(PROTECTED_INDEX) as snapshot:
        before = snapshot.hashes()
        write_new_json(workspace / "source-baseline.json", {
            "source": str(PROTECTED_INDEX), "hashes": before,
        })
        snapshot.copy_to(workspace / "working")
        print(f"Verified API snapshot: {workspace}", flush=True)
        child = None
        exit_code = 0
        try:
            child = subprocess.Popen(
                [sys.executable, "-B", "-m", "backend", "--workspace", str(workspace),
                 "--port", str(port)], cwd=Path(__file__).resolve().parents[1],
            )
            exit_code = child.wait()
        except KeyboardInterrupt:
            if child is not None:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait()
        finally:
            unchanged = snapshot.hashes() == before
            write_new_json(workspace / "shutdown-integrity.json", {
                "original_hashes_unchanged": unchanged, "worker_exit_code": exit_code,
            })
            if not unchanged:
                raise RuntimeError("Source integrity check failed")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        if args.workspace:
            serve_copy(args.workspace, args.port)
            return 0
        return launch(args.port)
    except Exception:
        print("API startup failed. Close index users, check dependencies and snapshot permissions.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
