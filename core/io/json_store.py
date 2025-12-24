from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


# -----------------------------
# Exceptions
# -----------------------------

@dataclass
class JsonStoreError(Exception):
    path: Path
    message: str
    cause: Optional[BaseException] = None

    def __str__(self) -> str:
        base = f"{self.message} (path={self.path})"
        if self.cause is not None:
            return f"{base}; cause={type(self.cause).__name__}: {self.cause}"
        return base


class JsonReadError(JsonStoreError):
    pass


class JsonWriteError(JsonStoreError):
    pass


# -----------------------------
# Public helpers
# -----------------------------

def ensure_dir(dir_path: Path) -> None:
    """
    Ensure a directory exists (mkdir -p).
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise JsonWriteError(path=dir_path, message="Failed to create directory", cause=e) from e


def read_json(path: Path, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Read JSON as dict.

    - If file doesn't exist: return `default` (or {}).
    - If JSON is invalid or not a JSON object: raise JsonReadError.
    """
    if default is None:
        default = {}

    try:
        if not path.exists():
            return dict(default)

        # Allow empty file -> treat as default (optional policy; safer for first-run)
        raw = path.read_text(encoding="utf-8").strip()
        if raw == "":
            return dict(default)

        data = json.loads(raw)
        if not isinstance(data, dict):
            raise JsonReadError(path=path, message="JSON root must be an object/dict")
        return data

    except JsonStoreError:
        raise
    except Exception as e:
        raise JsonReadError(path=path, message="Failed to read/parse JSON", cause=e) from e


def atomic_write_json(
    path: Path,
    data: Dict[str, Any],
    *,
    backup: bool = True,
    indent: int = 2,
    sort_keys: bool = True
) -> None:
    """
    Atomically write JSON to `path` (write temp file in same directory, then os.replace).
    Optionally create a .bak copy before replacing.

    Guarantees:
    - If write fails, original file remains intact.
    - Temp file is cleaned up on best-effort basis.

    Note:
    - Atomicity relies on os.replace within the same filesystem.  [Python docs: os.replace]
      https://docs.python.org/3/library/os.html#os.replace
    """
    if not isinstance(data, dict):
        raise JsonWriteError(path=path, message="atomic_write_json expects `data` to be a dict")

    parent = path.parent
    ensure_dir(parent)

    tmp_path = parent / f".{path.name}.{uuid4().hex}.tmp"
    bak_path = path.with_suffix(path.suffix + ".bak")

    try:
        # 1) Write temp file
        payload = json.dumps(
            data,
            ensure_ascii=False,
            indent=indent,
            sort_keys=sort_keys,
        )

        # Use binary write + fsync for better durability
        with open(tmp_path, "wb") as f:
            f.write(payload.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

        # 2) Backup old file (copy) if requested and exists
        if backup and path.exists():
            try:
                shutil.copy2(path, bak_path)
            except Exception as e:
                # Backup failure should not prevent saving; but we surface as write error
                raise JsonWriteError(path=bak_path, message="Failed to create backup file", cause=e) from e

        # 3) Atomic replace
        os.replace(tmp_path, path)  # atomic on same filesystem per Python docs

    except JsonStoreError:
        # keep our own error type
        raise
    except Exception as e:
        raise JsonWriteError(path=path, message="Failed to write JSON atomically", cause=e) from e
    finally:
        # Best-effort cleanup if temp still exists
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            # ignore cleanup errors
            pass


# -----------------------------
# Optional convenience utility
# -----------------------------

def now_iso_utc() -> str:
    """
    Minimal UTC ISO-8601 time string without external deps.
    Example: 2025-12-24T10:05:00Z
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())