import pytest
from fixtures.scripted import ScriptGateway, background_output

from math_research_agent.artifacts import EditorFailure
from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


async def test_background_all_prose_edited_and_metadata_persisted(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    paths.atomic_write("problem/original.md", "Find useful sign conditions.")
    output = background_output()
    output["literature"] = [
        dict(
            title="Elementary algebra",
            authors=["A. Author"],
            year=1900,
            relevance="REDUNDANT Sign lemmas.",
            key_results=["REDUNDANT [PROVED] x² ≥ 0"],
            doi="10.test/example",
            pdf_url=None,
        )
    ]
    output["references_bib"] = "@book{algebra, title={Elementary algebra}}"
    gw = ScriptGateway({"background": [output]})
    app = Orchestrator(db, paths, Config(), gw)
    await app.background()
    for name in [
        "problem/specification.md",
        "literature/AGENT_CONTEXT.md",
        "literature/literature_index.md",
        "reports/background_report.md",
        "literature/references.bib",
    ]:
        assert paths.resolve(name).exists()
    ref = db.one("SELECT * FROM literature")
    assert "REDUNDANT" not in ref["metadata_json"]
    assert "REDUNDANT" not in app.artifacts.content(ref["notes_artifact_id"])
    assert len(db.query("SELECT * FROM artifacts")) >= 6


async def test_background_failure_does_not_publish_partial_context(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    paths.atomic_write("problem/original.md", "A problem")
    gw = ScriptGateway({"background": [background_output()], "editor": [RuntimeError("offline")]})
    app = Orchestrator(db, paths, Config(), gw)
    with pytest.raises(EditorFailure):
        await app.background()
    assert not paths.resolve("problem/specification.md").exists()
    await app.retry(db.one("SELECT id FROM jobs WHERE job_type='BACKGROUND'")["id"])
    assert paths.resolve("problem/specification.md").exists()
    assert len([x for x in gw.inputs if x["role"] == "background"]) == 1


async def test_problem_cannot_change_under_cached_background_result(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    paths.atomic_write("problem/original.md", "Original problem")
    gw = ScriptGateway({"background": [background_output()], "editor": [RuntimeError("offline")]})
    app = Orchestrator(db, paths, Config(), gw)
    with pytest.raises(EditorFailure):
        await app.background()
    with pytest.raises(ValueError, match="Research has started"):
        app.set_problem("A different problem")
    assert paths.read("problem/original.md") == "Original problem"
