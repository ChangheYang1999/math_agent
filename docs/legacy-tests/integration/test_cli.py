import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from math_research_agent.db import Database
from math_research_agent.paths import Paths

runner = CliRunner()


def invoke(tmp_path: Path, args: list[str], input_text: str | None = None):
    from math_research_agent.cli import app

    return runner.invoke(app, ["--projects-root", str(tmp_path), *args], input=input_text)


def test_init_and_problem_set_need_no_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = invoke(tmp_path, ["init", "sign-study", "--title", "Sign Study"])

    assert result.exit_code == 0, result.output
    root = tmp_path / "sign-study"
    assert (root / "state.db").is_file()
    assert (root / "project.yaml").is_file()
    status = invoke(tmp_path, ["status", "sign-study"])
    assert status.exit_code == 0, status.output
    assert "Project: sign-study — Sign Study" in status.output
    assert "Last processed report: none" in status.output

    source = tmp_path / "problem.md"
    source.write_text("Determine whether every real square is nonnegative.\n", encoding="utf-8")
    result = invoke(tmp_path, ["problem", "set", "sign-study", "--file", str(source)])

    assert result.exit_code == 0, result.output
    assert (root / "problem" / "original.md").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_problem_set_accepts_stdin_dash(tmp_path: Path) -> None:
    assert invoke(tmp_path, ["init", "stdin-study", "--title", "Stdin Study"]).exit_code == 0

    result = invoke(
        tmp_path,
        ["problem", "set", "stdin-study", "--file", "-"],
        input_text="A problem supplied on standard input.\n",
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "stdin-study" / "problem" / "original.md").read_text(
        encoding="utf-8"
    ) == "A problem supplied on standard input.\n"


def test_status_json_is_machine_readable_without_gateway(tmp_path: Path, monkeypatch) -> None:
    import math_research_agent.cli as cli

    expected = {
        "project": {"slug": "status-study", "title": "Status Study"},
        "brain_cycle": None,
        "insights": {"ACTIVE": 0},
        "branches": {"QUEUED": 0},
        "inbox_count": 0,
        "jobs": [],
    }
    fake = SimpleNamespace(status=lambda: expected)
    monkeypatch.setattr(cli, "_open_project", lambda *args, **kwargs: fake)

    result = invoke(tmp_path, ["status", "status-study", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected


def test_inspect_prints_canonical_content_and_raw_path(tmp_path: Path, monkeypatch) -> None:
    import math_research_agent.cli as cli

    fake = SimpleNamespace(
        inspect=lambda kind, public_id: {
            "kind": kind,
            "public_id": public_id,
            "status": "REFUTED",
            "content": "The proposed claim has a counterexample.",
            "raw_paths": ["raw/branches/run.json"],
            "artifacts": [],
        }
    )
    monkeypatch.setattr(cli, "_open_project", lambda *args, **kwargs: fake)

    result = invoke(tmp_path, ["branch", "show", "inspect-study", "B-000002"])

    assert result.exit_code == 0, result.output
    assert "B-000002" in result.output
    assert "Raw: raw/branches/run.json" in result.output
    assert "The proposed claim has a counterexample." in result.output


def test_workers_report_retryable_job_ids_and_exit_nonzero(tmp_path: Path, monkeypatch) -> None:
    import math_research_agent.cli as cli

    class FakeApp:
        async def workers(self, max_concurrent=None):
            assert max_concurrent == 2
            return [
                {"job": 11, "result": "CONFIRMED", "error": None},
                {"job": 12, "result": None, "error": "RuntimeError"},
            ]

    monkeypatch.setattr(cli, "_open_project", lambda *args, **kwargs: FakeApp())

    result = invoke(tmp_path, ["workers", "worker-study", "--max-concurrent", "2"])

    assert result.exit_code == 1
    assert "Job 11" in result.output
    assert "Job 12" in result.output
    assert "RuntimeError" in result.output
    assert "Traceback" not in result.output


def test_retry_executes_job_and_recover_reports_count(tmp_path: Path, monkeypatch) -> None:
    import math_research_agent.cli as cli

    calls: list[int] = []

    class FakeApp:
        jobs = SimpleNamespace(recover=lambda: 3)

        async def retry(self, job_id):
            calls.append(job_id)
            return {"status": "COMPLETED"}

    monkeypatch.setattr(cli, "_open_project", lambda *args, **kwargs: FakeApp())

    retried = invoke(tmp_path, ["retry", "retry-study", "--job", "17"])
    recovered = invoke(tmp_path, ["recover", "retry-study"])

    assert retried.exit_code == 0, retried.output
    assert calls == [17]
    assert "completed" in retried.output.lower()
    assert recovered.exit_code == 0, recovered.output
    assert "3" in recovered.output


def test_value_error_is_concise_and_has_no_traceback(tmp_path: Path) -> None:
    result = invoke(tmp_path, ["status", "Missing_or_Invalid"])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "lowercase" in result.output
    assert "Traceback" not in result.output


def test_human_correction_becomes_inspectable_inbox_report_without_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert invoke(tmp_path, ["init", "correction-study", "--title", "Corrections"]).exit_code == 0
    correction = tmp_path / "correction.md"
    correction.write_text("The earlier sign argument omitted the endpoint.\n", encoding="utf-8")

    result = invoke(
        tmp_path,
        ["correction", "correction-study", "--file", str(correction)],
    )

    assert result.exit_code == 0, result.output
    assert "R-000001" in result.output
    shown = invoke(tmp_path, ["report", "show", "correction-study", "R-000001"])
    assert shown.exit_code == 0, shown.output
    assert "The earlier sign argument omitted the endpoint." in shown.output
    status = invoke(tmp_path, ["status", "correction-study", "--json"])
    assert json.loads(status.output)["inbox_count"] == 1


def test_invalid_config_error_names_the_field_without_dumping_input(tmp_path: Path) -> None:
    config = tmp_path / "invalid.yaml"
    config.write_text("limits:\n  max_probe_rounds: 0\n", encoding="utf-8")

    result = invoke(
        tmp_path,
        ["--config", str(config), "init", "config-study", "--title", "Config Study"],
    )

    assert result.exit_code == 1
    assert "limits.max_probe_rounds" in result.output
    assert "greater than 0" in result.output
    assert "input_value" not in result.output
    assert "Traceback" not in result.output


def test_offline_demo_runs_without_api_key_or_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = invoke(tmp_path, ["demo", "offline-signs"])

    assert result.exit_code == 0, result.output
    root = tmp_path / "offline-signs"
    db = Database(root / "state.db")
    assert [row["status"] for row in db.query("SELECT status FROM branches ORDER BY id")] == [
        "CONFIRMED",
        "REFUTED",
    ]
    assert len(db.query("SELECT * FROM brain_cycles WHERE status='COMPLETED'")) == 2
    assert len(db.query("SELECT * FROM reports")) == 2
    assert Paths(root).resolve("strategy/CURRENT_STRATEGY.md").is_file()
    assert "synthetic" in Paths(root).read("reports/background_report.md").lower()


def test_failed_branch_run_is_not_reported_as_completed(tmp_path):
    assert invoke(tmp_path, ["init", "failed-study", "--title", "Failed study"]).exit_code == 0
    db = Database(tmp_path / "failed-study" / "state.db")
    insight = db.execute(
        "INSERT INTO insights(public_id,summary,status) VALUES('I-000001','Human insight','ACTIVE')"
    )
    db.execute(
        "INSERT INTO branches(public_id,parent_insight_id,status) VALUES('B-000001',?,'FAILED')",
        (insight,),
    )
    db.execute(
        "INSERT INTO jobs(job_type,scope_type,scope_id,status,max_attempts,error) VALUES('RUN_BRANCH','branch','B-000001','FAILED',3,'GatewayInvocationError')"
    )
    result = invoke(tmp_path, ["branch", "run", "failed-study", "B-000001"])
    assert result.exit_code == 1
    assert "completed" not in result.output.lower()
    assert "retry" in result.output.lower()
    assert db.one("SELECT status FROM jobs")["status"] == "FAILED"


def test_recover_reports_jobs_recovered_at_startup(tmp_path):
    assert invoke(tmp_path, ["init", "recover-study", "--title", "Recovery"]).exit_code == 0
    db = Database(tmp_path / "recover-study" / "state.db")
    db.execute(
        "INSERT INTO jobs(job_type,scope_type,scope_id,status,max_attempts,lease_owner,lease_expires_at) VALUES('BACKGROUND','project','old','RUNNING',3,'expired',0)"
    )
    result = invoke(tmp_path, ["recover", "recover-study"])
    assert result.exit_code == 0
    assert "Recovered 1 expired job" in result.output
    assert db.one("SELECT status FROM jobs")["status"] == "QUEUED"
