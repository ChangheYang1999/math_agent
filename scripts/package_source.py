"""Build a small source ZIP from an explicit allowlist, excluding all research data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "README.md",
    "IMPLEMENTATION.md",
    "pyproject.toml",
    "config.example.yaml",
    ".env.example",
    ".gitignore",
    "bridge/tests/code_lines.mjs",
    "bridge/tests/resume_roles.mjs",
    "bridge/tests/final_answer.mjs",
    "bridge/tests/picker_activation.mjs",
    "bridge/tests/user_payload.mjs",
    "tests/dashboard_review_fixture.mjs",
]
FOLDERS = {
    "src/math_research_agent": {".py", ".html"},
    "prompts": {".md"},
    "tests": {".py"},
    "scripts": {".py"},
}


def package(destination: Path, summary: Path | None = None) -> Path:
    destination = destination.expanduser().resolve()
    candidates = [ROOT / name for name in FILES]
    # Package only accepted bridge patches. Failed candidates and machine-local
    # experiment artifacts remain outside the source distribution.
    bridge = ROOT / "bridge"
    manifest = json.loads((bridge / "manifest.json").read_text())
    candidates.extend([bridge / "README.md", bridge / "manifest.json"])
    for patch in manifest["accepted_patches"]:
        path = (bridge / patch["patch"]).resolve()
        if not path.is_relative_to(bridge.resolve()) or path.suffix != ".patch":
            raise ValueError("Accepted bridge patch must be a .patch file inside bridge/")
        candidates.append(path)
    for folder, suffixes in FOLDERS.items():
        candidates.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts
        )
    # Include the compact handoff at the archive root, not its detailed live
    # evidence directory. Preserve the original workspace artifact in place.
    if summary is None:
        summary = ROOT / "FIX_SUMMARY.md"
        if not summary.is_file():
            summary = ROOT / "experiments/bridge_xhigh_live/FIX_SUMMARY.md"
        summary_name = "FIX_SUMMARY.md"
    else:
        summary = summary.expanduser().resolve()
        if not summary.is_file():
            raise ValueError(f"Summary file does not exist: {summary}")
        summary_name = summary.name
    if summary.is_file():
        candidates.append(summary)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(candidates):
            if path.is_symlink():
                continue
            relative = Path(summary_name) if path == summary else path.relative_to(ROOT)
            archive.write(path, Path("math-agent") / relative)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--summary", type=Path, help="Compact release summary to include at archive root"
    )
    args = parser.parse_args()
    print(package(args.destination, args.summary))
