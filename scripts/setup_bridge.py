"""Install the pinned third-party bridge and only the reviewed local patches.

This command never starts a server, opens a browser, reloads an extension, or
reads credentials. An existing checkout with unexpected changes is left intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bridge"
DEFAULT_BASE = Path.home() / ".local/share/math-research-agent"
RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"


def run(args, *, cwd=None, env=None, capture=False):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    ).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_states(checkout, manifest):
    """Validate every file before applying anything; refuse partially edited files."""
    versions = {}
    targets = []
    for patch in manifest["accepted_patches"]:
        patch_path = BUNDLE / patch["patch"]
        if digest(patch_path) != patch["sha256"]:
            raise ValueError(f"Reviewed patch checksum differs: {patch['name']}")
        patch_targets = []
        for file in patch["files"]:
            # An explicit overlay may follow a reviewed patch on the same file.
            # Only the exact declared hash chain is accepted, never a fuzzy diff.
            chain = versions.setdefault(file["path"], [file["base_sha256"]])
            if chain[-1] != file["base_sha256"] or file["patched_sha256"] in chain:
                raise ValueError(f"Nonlinear accepted patch order: {file['path']}")
            chain.append(file["patched_sha256"])
            patch_targets.append((file["path"], len(chain) - 1))
        targets.append((patch, patch_targets))
    positions = {}
    for path, chain in versions.items():
        actual = digest(checkout / path)
        if actual not in chain:
            raise ValueError(f"Unreviewed source change: {path}")
        positions[path] = chain.index(actual)
    states = []
    for patch, patch_targets in targets:
        file_states = [
            "applied" if positions[path] >= target else "unapplied"
            for path, target in patch_targets
        ]
        if len(set(file_states)) != 1:
            raise ValueError(f"Partially applied patch: {patch['name']}")
        states.append((patch, file_states[0]))
    for file in manifest.get("guarded_files", []):
        if file["path"] not in versions and digest(checkout / file["path"]) != file["sha256"]:
            raise ValueError(f"Unaccepted source change: {file['path']}")
    changed = set(
        run(["git", "diff", "--name-only", "HEAD"], cwd=checkout, capture=True).splitlines()
    )
    unexpected = changed - versions.keys()
    if unexpected:
        raise ValueError("Unreviewed tracked changes: " + ", ".join(sorted(unexpected)))
    return states


def node_runtime(explicit):
    node = explicit or shutil.which("node")
    bundled = RUNTIME / "node/bin/node"
    if not node and bundled.is_file():
        node = str(bundled)
    if not node:
        raise ValueError("Node.js 20+ is required; install it or pass --node /path/to/node")
    version = run([node, "--version"], capture=True).strip()
    if int(version.lstrip("v").split(".")[0]) < 20:
        raise ValueError(f"Node.js 20+ is required; found {version}")
    env = os.environ.copy()
    env["PATH"] = str(Path(node).resolve().parent) + os.pathsep + env.get("PATH", "")
    return node, env


def npm_runtime(checkout, explicit):
    npm = explicit or shutil.which("npm")
    if npm:
        return [npm]
    # Codex's bundled runtime includes pnpm but may omit npm. Keep this pinned
    # bootstrap/cache beside the separate checkout, never inside project source.
    pnpm = shutil.which("pnpm")
    bundled = RUNTIME / "bin/fallback/pnpm"
    if not pnpm and bundled.is_file():
        pnpm = str(bundled)
    if not pnpm:
        raise ValueError("npm is required; install it or pass --npm /path/to/npm")
    cache = checkout.parent / ".mathagent-npm"
    return [
        pnpm,
        f"--config.store-dir={cache / 'store'}",
        f"--config.cache-dir={cache / 'cache'}",
        "dlx",
        "npm@11.6.2",
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=DEFAULT_BASE / "chatgpt-bridge")
    parser.add_argument("--extension-dir", type=Path, default=DEFAULT_BASE / "extension")
    parser.add_argument("--node", help="Node.js executable, if absent from PATH")
    parser.add_argument("--npm", help="npm executable, if absent from PATH")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only", action="store_true", help="Read-only revision/patch verification"
    )
    mode.add_argument(
        "--source-only",
        action="store_true",
        help="Apply patches and syntax-check; skip npm and deployment",
    )
    args = parser.parse_args()
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    checkout = args.checkout.expanduser().resolve()
    extension = args.extension_dir.expanduser().resolve()
    if not checkout.exists():
        if args.check_only:
            raise ValueError(f"Checkout does not exist: {checkout}")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--no-checkout", manifest["upstream_url"], checkout])
        run(["git", "checkout", "--detach", manifest["revision"]], cwd=checkout)
    if (
        run(["git", "rev-parse", "HEAD"], cwd=checkout, capture=True).strip()
        != manifest["revision"]
    ):
        raise ValueError(
            "Upstream revision differs; use a fresh separate checkout, without resetting this one"
        )
    remote = run(["git", "remote", "get-url", "origin"], cwd=checkout, capture=True).strip()
    if remote.removesuffix(".git") != manifest["upstream_url"].removesuffix(".git"):
        raise ValueError("Checkout origin differs from the reviewed upstream")
    states = patch_states(checkout, manifest)
    for patch, state in states:
        print(f"{patch['name']}: {state}")
        if not args.check_only and state == "unapplied":
            patch_path = BUNDLE / patch["patch"]
            run(["git", "apply", "--check", patch_path], cwd=checkout)
            run(["git", "apply", patch_path], cwd=checkout)
    if args.check_only:
        return
    node, env = node_runtime(args.node)
    for patch, state in patch_states(checkout, manifest):
        if state != "applied":
            raise ValueError(f"Patch failed to apply exactly: {patch['name']}")
        for file in patch["files"]:
            run([node, "--check", file["path"]], cwd=checkout, env=env)
    run([node, "--check", "src/index.js"], cwd=checkout, env=env)
    if args.source_only:
        print("Reviewed source and syntax checks passed; no dependencies or extension changed.")
        return
    npm = npm_runtime(checkout, args.npm)
    run([*npm, "ci", "--no-audit", "--no-fund"], cwd=checkout, env=env)
    run([*npm, "run", "check"], cwd=checkout, env=env)
    run([*npm, "run", "extension:install", "--", "--target", extension], cwd=checkout, env=env)
    print(f"Ready: {checkout}\nUnpacked extension: {extension}")
    print(
        "No browser/server was started or reloaded. Follow bridge/README.md for local startup and Chrome setup."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Bridge setup stopped: {error}") from error
