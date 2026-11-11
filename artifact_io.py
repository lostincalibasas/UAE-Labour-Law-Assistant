"""Create evaluation artifacts without replacing existing files."""

import json
from pathlib import Path


def require_new_output(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Output already exists: {path}. Choose a new --output path.")
    return path


def write_new_json(path, value):
    path = require_new_output(path)
    # Serialize before creating a file; exclusive creation also protects against
    # another process creating the destination after the preflight check.
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        file.write(payload)
