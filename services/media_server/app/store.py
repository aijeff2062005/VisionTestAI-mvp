"""On-disk object store (S3-shaped keys under MEDIA_ROOT)."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Collection
from pathlib import Path

_SAFE = re.compile(r"[^A-Za-z0-9._\-/=]+")


def safe_key(object_key: str) -> str:
    key = object_key.strip().lstrip("/")
    key = _SAFE.sub("_", key)
    if ".." in key.split("/"):
        raise ValueError("invalid object key")
    if not key:
        raise ValueError("empty object key")
    return key


class DiskStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, object_key: str) -> Path:
        key = safe_key(object_key)
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("path escape")
        return path

    def put(self, object_key: str, data: bytes, content_type: str) -> dict:
        path = self.path_for(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        meta = path.with_suffix(path.suffix + ".meta")
        meta.write_text(f"{content_type}\n{len(data)}\n", encoding="utf-8")
        return {
            "object_key": safe_key(object_key),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": content_type,
        }

    def get(self, object_key: str) -> tuple[bytes, str]:
        path = self.path_for(object_key)
        if not path.is_file():
            raise FileNotFoundError(object_key)
        content_type = "application/octet-stream"
        meta = path.with_suffix(path.suffix + ".meta")
        if meta.is_file():
            content_type = meta.read_text(encoding="utf-8").splitlines()[0] or content_type
        return path.read_bytes(), content_type

    def exists(self, object_key: str) -> bool:
        return self.path_for(object_key).is_file()

    def _meta_path(self, path: Path) -> Path:
        return path.with_suffix(path.suffix + ".meta")

    def _prune_empty(self, start: Path) -> None:
        root = self.root.resolve()
        current = start.resolve()
        while current != root and str(current).startswith(str(root)):
            if current.exists() and current.is_dir() and not any(current.iterdir()):
                current.rmdir()
                current = current.parent
                continue
            break

    def delete(self, object_key: str) -> bool:
        path = self.path_for(object_key)
        meta = self._meta_path(path)
        existed = path.is_file() or meta.is_file()
        if path.is_file():
            path.unlink()
        if meta.is_file():
            meta.unlink()
        if existed:
            self._prune_empty(path.parent)
        return existed

    def delete_session(self, session_id: str, stations: Collection[str] | None = None) -> list[str]:
        """Remove every object under {station}/{session_id}/… (sanitized match).

        stations limits the sweep to those station folders (one tenant); None sweeps all.
        """
        sid = (session_id or "").strip().strip("/")
        if not sid or "/" in sid or sid in {".", ".."}:
            raise ValueError("invalid session_id")
        target = safe_key(sid)
        if not target or target in {".", ".."}:
            raise ValueError("invalid session_id")

        deleted: list[str] = []
        root = self.root.resolve()
        if not root.is_dir():
            return deleted
        for station_dir in root.iterdir():
            if not station_dir.is_dir():
                continue
            if stations is not None and station_dir.name not in stations:
                continue
            for child in list(station_dir.iterdir()):
                if not child.is_dir():
                    continue
                if child.name != sid and safe_key(child.name) != target:
                    continue
                for file in child.rglob("*"):
                    if file.is_file() and not file.name.endswith(".meta"):
                        deleted.append(str(file.relative_to(root)))
                shutil.rmtree(child, ignore_errors=True)
        return deleted
