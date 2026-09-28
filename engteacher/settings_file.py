"""Small JSON settings files written by the GUI and read by the GUI and the hook."""

import json
import os
import tempfile
from pathlib import Path


def read_json_object(path: Path) -> dict:
    """Returns the saved object; a missing, unreadable, or malformed file reads as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json_atomic(path: Path, data: dict) -> None:
    """Writes atomically so a crash mid-save, or a concurrent reader, never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise
