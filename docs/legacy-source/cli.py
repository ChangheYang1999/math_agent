"""Small command-line interface for the persistent Research Tree."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .config import Config, load_config
from .paths import project_root
from .scheduler import Scheduler
from .store import Store

app = typer.Typer(help="Local Research Tree with persistent ChatGPT web conversations.")


@dataclass
class Options:
    config: Path | None
    projects_root: Path | None


def guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, sqlite3.Error, ValidationError, RuntimeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from None
        except KeyboardInterrupt:
            typer.echo("Stopped; committed research and pending turns are preserved.")
    return wrapped


@app.callback()
def main(
    context: typer.Context,
    config: Annotated[Path | None, typer.Option(help="Configuration YAML for new projects.")] = None,
    projects_root: Annotated[
        Path | None, typer.Option(help="Directory containing project folders.")
    ] = None,
) -> None:
    context.obj = Options(config, projects_root)


def configuration(context: typer.Context) -> Config:
    options = context.obj
    config = load_config(options.config)
    if options.projects_root is not None:
        config.projects_root = options.projects_root
    return config


def root_path(context: typer.Context, project: str) -> Path:
    return project_root(configuration(context).projects_root, project)


def open_scheduler(context: typer.Context, project: str, transport: str | None = None) -> Scheduler:
    store = Store(root_path(context, project))
    if transport is not None:
        if transport not in {"manual", "fake", "bridge"}:
            raise ValueError("Transport must be manual, fake or bridge")
        store.config.transport = transport
    return Scheduler(store)


@app.command()
@guarded
def init(
    context: typer.Context,
    project: str,
    goal: Annotated[str | None, typer.Option(help="English mathematical research goal.")] = None,
    file: Annotated[Path | None, typer.Option(help="UTF-8 goal file; '-' reads stdin.")] = None,
    transport: Annotated[str | None, typer.Option(help="manual, fake or bridge.")] = None,
    review: Annotated[bool, typer.Option("--review", help="Enable both human review gates.")] = False,
) -> None:
    if (goal is None) == (file is None):
        raise ValueError("Provide exactly one of --goal or --file")
    if file is not None:
        goal = typer.get_text_stream("stdin").read() if str(file) == "-" else file.read_text("utf-8")
    config = configuration(context)
    if transport is not None:
        config = config.model_copy(update={"transport": transport})
        config = Config.model_validate(config.model_dump())
    if review:
        config.manual_review_enabled = True
    root = root_path(context, project)
    Store.initialize(root, goal or "", config)
    typer.echo(f"Initialized Research Tree: {root}")
    typer.echo(f"Start the dashboard: mathagent dashboard {project}")


@app.command()
@guarded
def run(
    context: typer.Context,
    project: str,
    transport: Annotated[str | None, typer.Option(help="Override this process's transport.")] = None,
) -> None:
    research = open_scheduler(context, project, transport)
    typer.echo(f"Running {project}; press Ctrl+C to stop.")
    if research.store.config.transport == "manual":
        typer.echo("Manual relay requires the dashboard to bind chats and paste actual responses.")
    asyncio.run(research.run())


@app.command()
@guarded
def dashboard(
    context: typer.Context,
    project: str,
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8765,
    transport: Annotated[str | None, typer.Option(help="Override this process's transport.")] = None,
    open_browser: Annotated[bool, typer.Option("--open", help="Open the dashboard in a browser.")] = False,
) -> None:
    from .dashboard import serve

    research = open_scheduler(context, project, transport)
    typer.echo(f"Dashboard: http://127.0.0.1:{port}")
    typer.echo("The dashboard also runs the scheduler. Do not start a second runtime for this project.")
    asyncio.run(serve(research, port=port, open_browser=open_browser))


@app.command()
@guarded
def status(
    context: typer.Context,
    project: str,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full saved state.")] = False,
) -> None:
    snapshot = open_scheduler(context, project).snapshot()
    if as_json:
        typer.echo(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str))
        return
    settings = snapshot.get("settings", {})
    typer.echo(f"Project: {project}")
    typer.echo(f"Status: {settings.get('project_status', 'ACTIVE')}")
    typer.echo(f"Human review: {settings.get('manual_review_enabled', False)}")
    for node in snapshot.get("nodes", []):
        typer.echo(
            f"  {node['id']} [{node.get('role', '?')}] {node['status']} "
            f"weight={node.get('absolute_weight', 0):.3f} "
            f"target={node.get('target_leaves', 0)} round={node.get('round_counter', 0)}"
        )
    pending = [a for a in snapshot.get("approvals", []) if a["status"] == "PENDING"]
    typer.echo(f"Pending approvals: {len(pending)}")
    typer.echo(f"Recoverable errors: {len(snapshot.get('errors', []))}")
    typer.echo(f"Transport: {snapshot.get('transport', 'See saved session state')}")


@app.command()
@guarded
def recover(context: typer.Context, project: str) -> None:
    result = open_scheduler(context, project).recover()
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
@guarded
def demo(
    context: typer.Context,
    project: str = "research-tree-demo",
    rounds: Annotated[int, typer.Option(min=1, max=20, help="Completed report/parent pairs.")] = 2,
) -> None:
    from .demo import run_offline_demo

    root = asyncio.run(run_offline_demo(configuration(context).projects_root, project, rounds))
    typer.echo(f"Offline Research Tree demo completed: {root}")
    typer.echo("Fake transport verified the workflow; this did not contact ChatGPT web.")


if __name__ == "__main__":
    app()
