import sqlite3

import pytest

from math_research_agent.db import Database
from math_research_agent.ids import next_id, probe_id
from math_research_agent.paths import Paths, project_root, sanitize_filename


def test_project_paths_and_symlink_escape(tmp_path):
    root = project_root(tmp_path, "research")
    paths = Paths(root)
    paths.atomic_write("problem/original.md", "x")
    assert paths.read("problem/original.md") == "x"
    for bad in ["../other", "/tmp/other", "a/../../other"]:
        with pytest.raises(ValueError):
            paths.resolve(bad)
    (root / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        paths.resolve("link/outside.md")
    for bad in ["../bad", "/abs", "", "a/b", ".."]:
        with pytest.raises(ValueError):
            project_root(tmp_path, bad)
    assert "/" not in sanitize_filename("../../paper title")


def test_raw_immutable_and_atomic_replace(tmp_path):
    p = Paths(tmp_path)
    p.write_immutable("raw/a.md", "first")
    with pytest.raises(FileExistsError):
        p.write_immutable("raw/a.md", "second")
    assert p.read("raw/a.md") == "first"
    p.atomic_write("current.md", "one")
    p.atomic_write("current.md", "two")
    assert p.read("current.md") == "two"
    assert not list(tmp_path.glob("*.tmp"))


def test_migration_ids_and_reopen(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    with db.transaction() as c:
        assert next_id(c, "insight") == "I-000001"
        assert next_id(c, "insight") == "I-000002"
        assert next_id(c, "branch") == "B-000001"
    assert probe_id("B-000001", 2) == "Q-000001.2"
    assert Database(tmp_path / "state.db").project["slug"] == "test"
    with db.transaction() as c:
        assert next_id(c, "insight") == "I-000003"
    assert db.one("PRAGMA user_version")["user_version"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO branches(public_id,parent_insight_id,status) VALUES('B-9',999,'QUEUED')"
        )


def test_historical_verdict_immutable_and_probe_round_unique(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    i = db.execute(
        "INSERT INTO insights(public_id,summary,status) VALUES('I-000001','test','ACTIVE')"
    )
    b = db.execute(
        "INSERT INTO branches(public_id,parent_insight_id,status) VALUES('B-000001',?,'QUEUED')",
        (i,),
    )
    p = db.execute(
        "INSERT INTO probes(branch_id,public_id,round_number,status,verdict) VALUES(?,'Q-000001.1',1,'SOLVED','DISPROVED')",
        (b,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE probes SET verdict='PROVED' WHERE id=?", (p,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO probes(branch_id,public_id,round_number,status) VALUES(?,'Q-other',1,'DRAFTED')",
            (b,),
        )


def test_interrupted_immutable_write_never_exposes_partial_file(tmp_path, monkeypatch):
    import os

    paths = Paths(tmp_path)
    real_fsync = os.fsync

    def fail_sync(fd):
        raise OSError("Simulated disk failure before publication")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError):
        paths.write_immutable("raw/fixed-context.json", '{"complete": true}')
    assert not paths.resolve("raw/fixed-context.json").exists()
    monkeypatch.setattr(os, "fsync", real_fsync)
    paths.write_immutable("raw/fixed-context.json", '{"complete": true}')
    assert paths.read("raw/fixed-context.json") == '{"complete": true}'
