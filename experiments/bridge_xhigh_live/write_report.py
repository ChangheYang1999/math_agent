#!/usr/bin/env python3
"""Render only saved experiment evidence; stdout by default, no live calls."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
UNKNOWN = "NOT_VERIFIED"
FIELDS = "phase live_or_mock actual_model actual_effort browser_instance tab_id conversation_id turn/request_id started_at finished_at terminal_status correct_marker context_retained".split()


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def seconds(at):
    return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() if at else None


def cell(value):
    if value is None:
        return UNKNOWN
    return str(value).replace("|", "\\|").replace("\n", " ")


def fenced(value):
    fence = "~" * max(4, max((len(s) for s in str(value).split() if set(s) == {"~"}), default=0) + 1)
    return [fence + "text", str(value), fence]


def selected(checks, client, kind, boundary, before):
    if not boundary:
        return None
    matches = [c for c in checks if c.get("client_id") == client and c.get("kind") == kind
               and c.get("at") and (seconds(c["at"]) <= seconds(boundary) if before
                                    else seconds(c["at"]) >= seconds(boundary))]
    match = (max if before else min)(matches, key=lambda c: seconds(c["at"])) if matches else None
    current = (match or {}).get("current") or {}
    return {"at": match["at"], "label": current.get("label"), "id": current.get("id")} if match else None


def records(run):
    folder = BASE / "runs" / run
    manifest = read(folder / "manifest.json", {})
    evidence = {e.get("local_turn_id", path.stem): e for path in sorted((folder / "evidence").glob("*.json"))
                if (e := read(path, {}))}
    result = []
    for key in dict.fromkeys([*manifest.get("attempts", {}), *evidence]):
        attempt, saved = manifest.get("attempts", {}).get(key, {}), evidence.get(key, {})
        turn = saved.get("turn") or {}
        inp, response = turn.get("input") or {}, (turn.get("output") or {}).get("response") or {}
        rid = saved.get("request_id") or attempt.get("request_id")
        timing = {**saved.get("measurements", {}), **manifest.get("measurements", {}).get(rid, {})}
        dispatch = timing.get("dispatch_started", {}).get("at")
        terminal = timing.get("terminal_record_received", {}).get("at")
        client = inp.get("sourceClientId") or (attempt.get("binding") or {}).get("bridge_client_id")
        phase = attempt.get("phase") or "tree"
        binding = next((s for s in manifest.get("sessions", {}).get(phase, {}).values()
                        if s.get("bridge_client_id") == client), {})
        accepted = timing.get("terminal_accepted", {}).get("at")
        selection = {kind: {side: selected([c for c in manifest.get("selection_checks", [])
                                          if side == "pre" or (accepted and c.get("at")
                                              and seconds(c["at"]) <= seconds(accepted))], client, kind,
                                          dispatch if side == "pre" else terminal, side == "pre")
                            for side in ("pre", "post")} for kind in ("models", "efforts")}
        actual = {kind: "; ".join(f"{side}: {check['label']} ({check['id']})" if check else f"{side}: {UNKNOWN}"
                                  for side, check in sides.items()) for kind, sides in selection.items()}
        authoritative = turn.get("status") in {"completed", "completed_without_artifact"} and (
            response.get("requestId", response.get("id")) == rid and response.get("sourceClientId") == client)
        conversation = (response.get("session") or {}).get("id") or inp.get("sessionId") or binding.get("bridge_session_id")
        dispatched = bool(rid and dispatch)
        result.append({"run": run, "key": key, "phase": phase, "dispatched": dispatched, "row": [run + " / " + phase + ": " + key, "live" if dispatched else "NOT_DISPATCHED", actual["models"], actual["efforts"],
            manifest.get("browser_instance"), binding.get("browser_tab_id") or client, conversation, rid,
            dispatch, terminal, turn.get("status") or attempt.get("terminal_status") or "NOT_RUN",
            attempt.get("correct_marker"), attempt.get("context_retained")], "selection": selection,
            "timing": {**timing, "upstream_started_at": turn.get("startedAt"), "upstream_completed_at": turn.get("completedAt")},
            "prompt": inp.get("message") or attempt.get("prompt"), "answer": response.get("answer") if authoritative else None,
            "conversation_url": (response.get("session") or {}).get("url") or response.get("url"),
            "error": turn.get("error") or attempt.get("error"), "authoritative": authoritative,
            "evidence_path": str((folder / "evidence" / (key + ".json")).relative_to(BASE))})
    return manifest, result, read(folder / "tree_summary.json", {})


def render(runs, requested_status, notes):
    datasets = [(run, *records(run)) for run in runs]
    latest, all_records = datasets[-1][1], [record for _, _, records_, _ in datasets for record in records_]
    phases = latest.get("phases", {})
    phase2 = [r for r in datasets[-1][2] if r["key"].startswith("parallel-")]
    def verified(record):
        return record["authoritative"] and record["row"][11] is True and all(
            (check or {}).get("label") in {"GPT-6", "GPT-6 Thinking"}
            for check in record["selection"]["models"].values()) and all(
            (check or {}).get("id") == "xhigh" for check in record["selection"]["efforts"].values())
    passed = phases.get("smoke_pass") and phases.get("phase2_pass") and all(
        any(r["key"].startswith(f"parallel-{label}-") and verified(r)
            and (("context" in r["key"]) == context)
            and (not context or r["row"][12] is True) for r in phase2)
        for label in "ABC" for context in (False, True))
    status = "LIVE PASS" if passed else requested_status or ("PARTIAL" if any(r["authoritative"] for r in all_records) else "IN_PROGRESS")
    tree_audit = read(BASE / "tree_audit.json", {})
    tree_pairs = tree_audit.get("counts", {}).get("parent_responses", phases.get("tree_pairs_completed", 0))
    target = tree_audit.get("extended_target_pairs", 4)
    cleanup = read(BASE / "final_cleanup.json", {})
    lines = ["# Existing Chrome / Extra High live experiment", "", f"Three-conversation browser test: **{status}**.", "",
             f"Generated from saved evidence at {datetime.now(UTC).isoformat()}. Runs: {', '.join(runs)}.",
             f"Live smoke/context: {phases.get('smoke_pass', UNKNOWN)}. Three independent proof replies: {phases.get('parallel_outputs_pass', UNKNOWN)}. Per-conversation context: {phases.get('context_pass', UNKNOWN)}.",
             f"Proof requests shared {phases.get('three_way_in_flight_overlap_seconds', UNKNOWN)} seconds in flight; request-scoped observed generation overlap was {phases.get('proof_generation_evidence', {}).get('observed_overlap_seconds', UNKNOWN)} seconds. These are separate measurements.",
             f"Requested mode: GPT-6 Thinking / Extra High. Actual exact model picker label: {latest.get('actual_model_label', UNKNOWN)}; actual effort: Extra High (xhigh) where the pre/post checks below verify it. The UI label is recorded without adding a Thinking suffix.",
             f"Actual tree protocol: {tree_pairs} complete report/parent-response pairs. Required minimum: {tree_audit.get('minimum_target_pairs', 2)}; minimum_tree_pass: {tree_audit.get('minimum_tree_pass', UNKNOWN)}. Extended target: {target} pairs; remaining: {max(0, target - tree_pairs)}. Tree status is separate from the three-tab LIVE PASS.",
             ("Extended tree outcome: INCOMPLETE. Long parent-prompt preparation stopped before confirmed submission; the unsuccessful composer candidate was reverted."
              if cleanup.get("tree_extended_status") == "INCOMPLETE_LONG_PARENT_PROMPT_PREPARATION" else "Extended tree outcome is recorded in the audit below."),
             "The turn table and terminal-answer section use authoritative stored terminal records. A separate appendix labels later read-only DOM recovery copies. Failed attempts remain preserved; previews and local tests do not count as live replies.", "",
             "| " + " | ".join(FIELDS) + " |", "| " + " | ".join(["---"] * len(FIELDS)) + " |"]
    for record in all_records:
        lines.append("| " + " | ".join(cell(v) for v in record["row"]) + " |")
    for group in ("parallel", "tree"):
        if not any(r["phase"] == group for r in all_records):
            lines.append("| " + " | ".join([group, "NOT_RUN", *([UNKNOWN] * 8), "NOT_RUN", UNKNOWN, UNKNOWN]) + " |")
    lines += ["", "## Concurrency and Research Tree protocol", ""]
    for run, manifest, _, tree in datasets:
        p = manifest.get("phases", {})
        lines += [f"### {run}", "", "Saved phase verdicts and measured evidence:", *fenced(json.dumps(p, indent=2)), ""]
        lines += ["HTTP in-flight overlap and observed generation are separate measurements. Generation intervals infer activity between consecutive fresh request-matched observations at <=2-second resolution, bounded by actual dispatch and terminal completion. Cached singleton flags, missing intervals, and serialized generation cannot establish a parallel pass.", ""]
        if p.get("parallel_outputs_pass") and p.get("three_way_in_flight_overlap_seconds") == 0:
            lines += ["MULTI_TAB_WORKS_BUT_NOT_CONCURRENT: all three replies were retrieved, but measured in-flight intervals did not share overlap.", ""]
        elif p.get("parallel_outputs_pass") and not p.get("actual_three_way_generation_observed"):
            lines += ["Multi-tab replies were retrieved; simultaneous generation remains NOT_VERIFIED. Missing telemetry alone does not establish serialization.", ""]
        if tree:
            rounds = {r["id"]: r for r in tree.get("rounds", [])}
            links = [{"round": p["round_id"], "next_round": p["next_round_id"],
                      "saved_report": bool(rounds.get(p["round_id"], {}).get("report")),
                      "next_round_links_back": rounds.get(p["next_round_id"], {}).get("previous_round_id") == p["round_id"]}
                     for p in tree.get("parent_responses", [])]
            lines += ["Actual saved tree report/parent-response links (direct bridge tests alone do not establish tree integration):", *fenced(json.dumps(links, indent=2)), ""]
        else:
            lines += ["Actual Research Tree protocol: NOT_RUN; no saved tree summary exists.", ""]
    if tree_audit:
        summary = {key: tree_audit.get(key, UNKNOWN) for key in (
            "observed_at", "status", "minimum_tree_pass", "counts", "terminal_counts", "extended_remaining_pairs", "round2_dispatch_order", "conversation_isolation", "leaf_overlap_by_round", "concerns", "limits")}
        lines += ["Independent read-only tree audit: [tree_audit.json](tree_audit.json). Counts and ordering reflect its stated snapshot time:", *fenced(json.dumps(summary, indent=2)), ""]
    lines += ["## Exact prompts, terminal replies, selection checks and timestamps", ""]
    for r in all_records:
        lines += [f"### {r['run']} / {r['key']}", "", f"Evidence: [{r['evidence_path']}]({r['evidence_path']}).",
                  f"Conversation URL: {r['conversation_url'] or UNKNOWN}", "", "Selection snapshots and exact timing:",
                  *fenced(json.dumps({"selection": r["selection"], "timing": r["timing"]}, indent=2)), "",
                  f"Intended prompt; dispatch recorded: {'yes' if r['dispatched'] else 'no'}:", *fenced(r["prompt"] or "NOT_RUN"), "", "Authoritative complete terminal answer:",
                  *fenced(r["answer"] if r["answer"] is not None else "NOT_VERIFIED: no authoritative complete reply"), ""]
        if r["error"]:
            lines += ["Preserved failure:", *fenced(json.dumps(r["error"], indent=2)), ""]
    recovery, recovery_audit = read(BASE / "math_dom_recovery.json", []), read(BASE / "math_dom_recovery_audit.json", {})
    if recovery:
        lines += ["## Math-preserving copies of the six original replies", "",
                  "Original terminal text remains immutable above. Earlier extraction flattened some KaTeX radicals, fractions and exponents. These are complete post-fix read-only DOM copies of the same assistant turns, not new terminal results and not new inference.",
                  f"Independent recovery audit: all checks passed={recovery_audit.get('all_passed', UNKNOWN)}; complete annotation comparisons={recovery_audit.get('complete_annotation_comparisons', UNKNOWN)}. See [math_dom_recovery_audit.json](math_dom_recovery_audit.json).", ""]
        for copy in recovery:
            result = (copy.get("response") or {}).get("result") or {}
            audit = next((a for a in recovery_audit.get("results", []) if a.get("label") == copy.get("label") and a.get("kind") == copy.get("kind")), {})
            identity = {"original_request_id": audit.get("original_request_id", UNKNOWN),
                        "assistant_turn_key": result.get("turnKey", UNKNOWN), "source_client_id": result.get("sourceClientId", UNKNOWN),
                        "conversation_id": (result.get("session") or {}).get("id", UNKNOWN),
                        "copied_at": copy.get("at", UNKNOWN), "inference_performed": copy.get("inference_performed", UNKNOWN),
                        "original_terminal_unchanged": copy.get("original_terminal_unchanged", UNKNOWN)}
            lines += [f"### Session {copy.get('label', UNKNOWN)} / {copy.get('kind', UNKNOWN)} — read-only DOM copy", "",
                      *fenced(json.dumps(identity, indent=2)), "", *fenced(result.get("answer", UNKNOWN)), ""]
    lines += ["## Setup, repairs and remaining work", "", "Environment details: [ENVIRONMENT.md](ENVIRONMENT.md). Production model defaults remain separate from the disposable runner's explicitly selected model label.", ""]
    for path in sorted(BASE.glob("*.patch")):
        if path.name == "upstream_composer.patch":
            state = "NOT APPLIED" if cleanup.get("composer_candidate_applied") is False else "final application state NOT_VERIFIED"
            lines.append(f"- Unproven candidate patch: [{path.name}]({path.name}) — {state}; the extended live test did not pass with this candidate.")
        else:
            lines.append(f"- Saved source patch: [{path.name}]({path.name}).")
    connected = read(BASE / "phase0_connected.json", {})
    if connected:
        lines.append(f"- Extension connection recorded at {connected.get('observed_at', UNKNOWN)}.")
        for endpoint in ("/models", "/efforts"):
            result = connected.get("endpoints", {}).get(endpoint, {})
            if result.get("detail"):
                lines.append(f"- Initial connected {endpoint} discovery: HTTP {result.get('http_status', UNKNOWN)}, {result['detail']}")
    history = BASE / "bridge_restart_history.jsonl"
    restarts = [json.loads(line) for line in history.read_text().splitlines() if line.strip()] if history.exists() else [read(BASE / "bridge_restart.json", {})]
    for restart in restarts:
        if restart:
            lines.append(f"- Local bridge restart recorded at {restart.get('restarted_at', restart.get('at', UNKNOWN))}; endpoint {restart.get('base_url', UNKNOWN)}. This records a server restart, not a browser restart.")
    lines += ["- Experiment source files: run_experiment.py, test_runner.py, write_report.py and README.md.",
              *["- " + note for note in notes], "", f"Final workload shutdown: {'verified by final_cleanup.json' if cleanup.get('workloads_stopped') is True else UNKNOWN}."]
    if cleanup:
        state = {key: cleanup[key] for key in ("observed_at", "workloads_stopped", "scheduler_running", "active_requests", "pending_commands", "bridge_pending_requests", "bridge_pending_commands", "test_tabs_preserved", "original_tab_preserved", "production_defaults_restored", "loopback_only", "composer_candidate_applied") if key in cleanup}
        lines += ["Saved cleanup state: [final_cleanup.json](final_cleanup.json).", *fenced(json.dumps(state, indent=2))]
    lines += ["", "Next steps: " + ("Inspect the retained test tabs and tree evidence; refer to the recorded cleanup state. No further inference is needed to inspect these results." if passed else "Resolve the latest preserved failure, then complete the gated smoke, three-tab proof/context, and optional tree phases. Do not replay uncertain requests or count mock tests as live results."), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", dest="runs")
    parser.add_argument("--status", choices=("IN_PROGRESS", "PARTIAL", "BLOCKED"))
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = render(args.runs or ["20261014-live", "20261014-live-r2"], args.status, args.note)
    for name in ("MATHAGENT_BRIDGE_API_TOKEN", "API_TOKEN", "BRIDGE_TOKEN"):
        if os.getenv(name):
            result = result.replace(os.environ[name], "[REDACTED]")
    if args.output:
        args.output.write_text(result)
        print(f"Saved {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
