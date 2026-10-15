"""Short SQLite transactions; connections are never held across model awaits."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .migrations import migrate


class Database:
    def __init__(self, path: Path):
        self.path = path.resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Project database does not exist: {self.path}")
        with self.connection() as connection:
            migrate(connection)

    @classmethod
    def initialize(cls, root: Path, slug: str, title: str) -> Database:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "state.db"
        # Exclusive creation prevents init from overwriting an existing project.
        with path.open("xb"):
            pass
        database = cls(path)
        database.execute(
            "INSERT INTO projects(id,slug,title,root_path) VALUES(1,?,?,?)",
            (slug, title, str(root.resolve())),
        )
        return database

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, params)
            return cursor.lastrowid or 0

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @property
    def project(self) -> dict[str, Any]:
        row = self.one("SELECT * FROM projects WHERE id=1")
        if row is None:
            raise ValueError("Project database is not initialized")
        return row
