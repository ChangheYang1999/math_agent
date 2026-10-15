"""The sole gateway from generated research prose to canonical files."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any
from uuid import uuid4

from .db import Database
from .editor_service import EditorFailure, EditorService
from .execution import check_owner, run_metadata
from .paths import Paths

__all__ = ["ArtifactService", "EditorFailure"]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ArtifactService:
    def __init__(self, db: Database, paths: Paths, gateway: Any, fail_closed: bool = True):
        self.db, self.paths = db, paths
        self.editor = EditorService(gateway)
        self.fail_closed = fail_closed

    def _execute(self, sql: str, params: tuple = ()) -> int:
        with self.db.transaction() as connection:
            check_owner(connection)
            return connection.execute(sql, params).lastrowid or 0

    async def persist(
        self,
        *,
        key: str,
        kind: str,
        scope: str,
        raw_content: str,
        mode: str,
        destination: str,
        metadata: dict[str, str] | None = None,
        model_run_id: str | None = None,
        publish: bool = True,
    ) -> dict:
        self.paths.resolve(destination)
        if mode not in {"proof_safe", "aggressive", "prompt"}:
            raise ValueError("Unknown editing mode")
        metadata = {**(metadata or {}), **run_metadata()}
        row = self.db.one("SELECT * FROM artifacts WHERE logical_key=?", (key,))
        if row is None:
            artifact_id = uuid4().hex
            raw_path = f"raw/artifacts/{artifact_id}.md"
            self.paths.write_immutable(raw_path, raw_content)
            try:
                self._execute(
                    "INSERT INTO artifacts(id,logical_key,kind,scope_type,scope_id,raw_path,destination,"
                    "editor_mode,content_sha256_raw,model_run_id,status,metadata_json) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,'RAW',?)",
                    (
                        artifact_id,
                        key,
                        kind,
                        kind,
                        scope,
                        raw_path,
                        destination,
                        mode,
                        digest(raw_content),
                        model_run_id,
                        json.dumps(metadata),
                    ),
                )
            except sqlite3.IntegrityError:
                # A concurrent owner may have persisted the same logical action.
                # The losing raw file remains an immutable audit artifact.
                pass
            row = self.db.one("SELECT * FROM artifacts WHERE logical_key=?", (key,))
        assert row is not None
        if row["content_sha256_raw"] != digest(raw_content):
            raise ValueError("Logical artifact key reused with different raw content")
        if row["destination"] != destination or row["editor_mode"] != mode:
            raise ValueError("Logical artifact destination or mode changed")
        if row["status"] not in {"EDITED", "UNEDITED_ALLOWED"}:
            # Interrupted EDITING resumes its exact action. A rejected/failed edit
            # receives a new bounded attempt, while preserving the original raw text.
            if row["status"] != "EDITING":
                self._execute(
                    "UPDATE artifacts SET edit_attempts=edit_attempts+1,status='EDITING' WHERE id=?",
                    (row["id"],),
                )
                row = self.db.one("SELECT * FROM artifacts WHERE id=?", (row["id"],))
                assert row is not None
            try:
                result = await self.editor.edit(
                    key=f"{row['id']}:{row['edit_attempts']}",
                    content=raw_content,
                    kind=kind,
                    mode=mode,
                    metadata=metadata,
                )
                edited, issues, editor_run = (
                    result.output.edited_content,
                    result.output.consistency_issues,
                    result.run_id,
                )
                status = "EDITED"
            except Exception as exc:
                self._execute("UPDATE artifacts SET status='EDIT_FAILED' WHERE id=?", (row["id"],))
                if self.fail_closed:
                    raise EditorFailure(
                        f"Editing failed for artifact {row['id']}; raw retained"
                    ) from exc
                edited, issues, editor_run = (
                    raw_content,
                    ["Explicit fail-open: unedited text"],
                    None,
                )
                status = "UNEDITED_ALLOWED"
            check_owner()
            edited_path = f"artifacts/{row['id']}/edit-{row['edit_attempts']}.md"
            # This version is never reused for a different raw source.
            self.paths.atomic_write(edited_path, edited)
            self._execute(
                "UPDATE artifacts SET edited_path=?,content_sha256_edited=?,edited_at=CURRENT_TIMESTAMP,"
                "editor_run_id=?,status=?,consistency_issues=? WHERE id=?",
                (edited_path, digest(edited), editor_run, status, json.dumps(issues), row["id"]),
            )
            row = self.db.one("SELECT * FROM artifacts WHERE id=?", (row["id"],))
            assert row is not None
        if publish:
            self.publish(row)
        return row

    def publish(self, row: dict) -> None:
        if row["status"] not in {"EDITED", "UNEDITED_ALLOWED"} or not row["edited_path"]:
            raise EditorFailure("Artifact is not ready for downstream use")
        content = self.paths.read(row["edited_path"])
        if digest(content) != row["content_sha256_edited"]:
            raise ValueError("Canonical artifact hash mismatch")
        with self.db.transaction() as connection:
            check_owner(connection)
            self.paths.atomic_write(row["destination"], content)

    def content(self, artifact_id: str) -> str:
        row = self.db.one("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
        if row is None or row["status"] not in {"EDITED", "UNEDITED_ALLOWED"}:
            raise EditorFailure("Canonical edited artifact unavailable")
        content = self.paths.read(row["edited_path"])
        if digest(content) != row["content_sha256_edited"]:
            raise ValueError("Canonical artifact hash mismatch")
        return content
