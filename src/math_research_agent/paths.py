"""Code-controlled paths and durable atomic artifact writes."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


def project_root(projects_root: Path, slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Project slug must contain lowercase letters, numbers and single hyphens")
    base = projects_root.expanduser().resolve()
    result = (base / slug).resolve()
    if result.parent != base:
        raise ValueError("Project escapes projects root")
    return result


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")[:120] or "paper"


class Paths:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("Expected a project-relative path without traversal")
        result = (self.root / path).resolve()
        if not result.is_relative_to(self.root) or result == self.root:
            raise ValueError("Path escapes project root")
        return result

    def read(self, relative: str) -> str:
        return self.resolve(relative).read_text(encoding="utf-8")

    def write_immutable(self, relative: str, content: str | bytes) -> Path:
        return self._write(relative, content, exclusive=True)

    def atomic_write(self, relative: str, content: str | bytes) -> Path:
        return self._write(relative, content, exclusive=False)

    def _write(self, relative: str, content: str | bytes, *, exclusive: bool) -> Path:
        path = self.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if exclusive:
                # Linking a fully synced temporary file publishes atomically without
                # replacing a pre-existing immutable record.
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path
