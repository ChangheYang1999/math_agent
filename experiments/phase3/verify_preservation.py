"""Read-only provenance check; writes only a new Phase 3 evidence file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = Path("/private/tmp/mathagent-upstream-bridge")
FRESH = Path("/private/tmp/mathagent-eight-patch-check-6pevzfl1/checkout")
EXTENSION = Path("/private/tmp/mathagent-live-extension")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "experiments/phase3/bridge_validation.json"
    )
    parser.add_argument("--fresh-checkout", type=Path, default=FRESH)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "bridge/manifest.json").read_text())
    expected = {}
    patch_checks = {}
    for patch in manifest["accepted_patches"]:
        patch_checks[patch["name"]] = (
            sha((ROOT / "bridge" / patch["patch"]).read_bytes()) == patch["sha256"]
        )
        for file in patch["files"]:
            expected[file["path"]] = file["patched_sha256"]
    source_checks = {
        str(checkout): {
            "revision": git(checkout, "rev-parse", "HEAD"),
            "source_hashes_match": {
                name: sha((checkout / name).read_bytes()) == value
                for name, value in expected.items()
            },
        }
        for checkout in (ACTIVE, args.fresh_checkout)
    }
    prefix = "tools/chrome-bridge-extension/"
    extension_checks = {
        name.removeprefix(prefix): sha((EXTENSION / name.removeprefix(prefix)).read_bytes())
        == value
        for name, value in expected.items()
        if name.startswith(prefix)
    }
    baseline = json.loads((ROOT / "experiments/phase3/baseline.json").read_text())
    unchanged = {
        name: sha((ROOT / name).read_bytes()) == value
        for name, value in baseline["sha256"].items()
        if name.startswith(("bridge/", "experiments/bridge_xhigh_live/"))
        or name in {"FIX_SUMMARY.md", "config.example.yaml"}
    }
    with ZipFile(ROOT / "dist/math-agent-long-prompt-fix.zip") as archive:
        original_bytes = archive.read("math-agent/bridge/manifest.json")
    if sha(original_bytes) != baseline["sha256"]["bridge/manifest.json"]:
        raise ValueError("Historical manifest copy does not match the saved baseline hash")
    original_manifest = json.loads(original_bytes)
    manifest_extension = {
        "whole_manifest_unchanged": unchanged["bridge/manifest.json"],
        "original_eight_entries_identical": original_manifest["accepted_patches"]
        == manifest["accepted_patches"][:8],
        "pinned_revision_unchanged": original_manifest["revision"] == manifest["revision"],
        "exactly_one_additional_patch": len(manifest["accepted_patches"]) == 9
        and manifest["accepted_patches"][8]["name"] == "resume_roles",
        "additional_patch_verification": "OFFLINE_ONLY; active runtime remains unchanged",
    }
    # A read transaction includes any saved WAL while opening in mode=ro avoids
    # Store migrations, settings updates, or scheduler recovery on historical data.
    historical = ROOT / "experiments/bridge_xhigh_live/runs/20261014-live-r2/projects/tree/tree.db"
    connection = sqlite3.connect(historical.as_uri() + "?mode=ro", uri=True)
    connection.execute("BEGIN")
    tables = {}
    for (name,) in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
        encoded = sorted(
            json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows
        )
        tables[name] = {"rows": len(rows), "sha256": sha("\n".join(encoded).encode())}
    connection.close()
    result = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Read-only local source and historical DB; no browser/network/model calls.",
        "pinned_revision": manifest["revision"],
        "accepted_patch_count": len(patch_checks),
        "patch_checksums_match": patch_checks,
        "source_checkouts": source_checks,
        "installed_extension_hashes_match": extension_checks,
        "baseline_artifacts_unchanged": unchanged,
        "manifest_extension": manifest_extension,
        "deployment_note": "New resume_roles expected hashes differ on the unchanged eight-patch active runtime; this is not a claimed deployment.",
        "active_extra_tracked_files": sorted(
            set(git(ACTIVE, "diff", "--name-only", "HEAD").splitlines()) - expected.keys()
        ),
        "active_lockfile_note": (
            "Strict check-only refuses package-lock.json: one added peer=true metadata line "
            "for picomatch. Dependency version/integrity unchanged. File left untouched; "
            "cause not inferred from metadata alone."
        ),
        "fresh_check_only": "Use resume_roles_validation.json for the separately executed strict nine-patch setup checks.",
        "historical_tree": {"path": str(historical.relative_to(ROOT)), "tables": tables},
    }
    destination = args.output
    if destination.exists():
        raise SystemExit(
            "Evidence file already exists; preserve it and choose a distinct recheck path."
        )
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
