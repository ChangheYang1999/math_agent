import hashlib
import json
from types import SimpleNamespace

import pytest

from math_research_agent.artifacts import ArtifactService, EditorFailure
from math_research_agent.db import Database
from math_research_agent.paths import Paths


class EditorStub:
    def __init__(self, paths, fail=False):
        self.paths = paths
        self.fail = fail

    async def run_structured(self, **kwargs):
        # Reading real raw files at invocation catches reversed write/editor order.
        payload = json.loads(kwargs["input_text"])
        assert any(
            p.read_text() == payload["raw_content"]
            for p in self.paths.root.glob("raw/artifacts/*.md")
        )
        if self.fail:
            raise RuntimeError("editor unavailable")
        return SimpleNamespace(
            output=kwargs["output_type"](
                edited_content=payload["raw_content"].replace("REDUNDANT ", ""),
                consistency_issues=["Check endpoint"]
                if "endpoint" in payload["raw_content"]
                else [],
            ),
            run_id="editor-test",
        )


async def test_artifact_recovery_is_raw_immutable_and_fail_closed(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    editor = EditorStub(paths, fail=True)
    service = ArtifactService(db, paths, editor, fail_closed=True)
    args = dict(
        key="solver:1",
        kind="solver",
        scope="Q-000001.1",
        raw_content="REDUNDANT Proof endpoint.",
        mode="proof_safe",
        destination="branches/B-000001/Q-000001.1/solver_report.md",
        metadata={"verdict": "PROVED"},
    )
    with pytest.raises(EditorFailure):
        await service.persist(**args)
    row = db.one("SELECT * FROM artifacts")
    assert row["status"] == "EDIT_FAILED"
    assert paths.read(row["raw_path"]) == "REDUNDANT Proof endpoint."
    assert not paths.resolve(args["destination"]).exists()
    editor.fail = False
    fixed = await service.persist(**args)
    assert fixed["id"] == row["id"]
    assert paths.read(fixed["edited_path"]) == "Proof endpoint."
    assert fixed["content_sha256_raw"] == hashlib.sha256(b"REDUNDANT Proof endpoint.").hexdigest()
    assert json.loads(fixed["consistency_issues"]) == ["Check endpoint"]
    assert json.loads(fixed["metadata_json"])["verdict"] == "PROVED"
    assert len(db.query("SELECT * FROM artifacts")) == 1
    with pytest.raises(ValueError, match="different raw"):
        await service.persist(**{**args, "raw_content": "different proof"})


async def test_unpublished_artifact_is_not_canonical_until_commit(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    service = ArtifactService(db, paths, EditorStub(paths))
    row = await service.persist(
        key="cycle:1",
        kind="strategy",
        scope="C-1",
        raw_content="New strategy",
        mode="aggressive",
        destination="strategy/CURRENT_STRATEGY.md",
        publish=False,
    )
    assert not paths.resolve(row["destination"]).exists()
    service.publish(row)
    assert paths.read(row["destination"]) == "New strategy"
