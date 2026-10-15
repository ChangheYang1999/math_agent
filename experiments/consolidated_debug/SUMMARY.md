# Consolidated debugging — actual results

**Completed:** focused fixes and the bounded real-browser experiment. Two independent genuine **GPT-6 Pro** Leaves each completed three rounds; their persistent **GPT-6 Extra High** Parent saved all **six report/assessment pairs** and concrete next prompts. Final Parent completion: **2026-10-15 10:10:31.517 UTC**. The runner exited successfully; both Leaves are PAUSED, both fourth-round prompts are saved but undispatched, and the Bridge is idle.

This was a recovered run, not a failure-free run. All original capture errors remain visible. The ledger contains **14/16 reservations**: 13 distinct submitted inference requests and one proven pre-delivery busy rejection. No uncertain submitted request was repeated. The existing Chrome/profile was reused; no API inference or simulated response substituted for these results.

| Check | Actual verdict |
| --- | --- |
| Exact Pro picker and inference | LIVE_PASS; physically selected GPT-6 plus Pro, verified before/after, authenticated genuine Pro finals |
| Two Leaves × three rounds, six exact Parent pairs | LIVE_PASS; schema IDs, saved links and mandatory event ordering valid |
| Long input and new rich user-message layout | LIVE_PASS; normal 28,618-character input; patched rich-root 23,768-character input auto-expanded and matched its complete hash before one confirmed Send |
| Original repeated approval popup | LIVE_PASS for local UI diagnosis/repair; all 12 real user approvals preserved; rapid distinct gates had looked identical |
| Genuine-provider manual-review cycle | Prompt personally HUMAN_APPROVED at 8:21:26 a.m. PDT; refresh preserves APPROVED / WAITING_FOR_DISPATCH; genuine Pro/report approval cycle NOT_RUN |
| Original uncertain Parent recovery | LIVE_PASS for exact audited reconciliation; original failure retained; historical sibling obligation still pending |
| Research report publication | Initial LIVE_FAIL in experiment's deferred ordering; focused harness fix and zero-inference append-only republication passed |
| Concurrent native generation | LIVE_PASS for two owned tabs in the captured 149 ms observation window; no sustained or three-way generation claim |
| Persistent independent node context | LIVE_PASS for stable distinct conversation bindings and supplied durable round context; unaided new recall NOT_RUN |
| Recursive promotion, weights/capacity, optional communication | OFFLINE_PASS; no new live recursive promotion or forced messages/splitting |
| Ninth resume_roles handler | OFFLINE_PASS and deployed; exact live request.resume execution NOT_RUN |
| Legacy plain-Markdown string fidelity | LIVE_FAIL/KNOWN_FAIL for underscore/emphasis reconstruction; future fenced JSON content fidelity passed |

## Fixes and preserved evidence

The dashboard now identifies exact node/round/type/version/hash and queue position, returns authoritative approval receipts, distinguishes approval from dispatch, disables submitting controls, shows HTTP errors and suppresses stale-poll reopening. The user's original round-one version 2 was approved; the current 8766 item is a distinct round-seven/version-two prompt. [Approval investigation](APPROVAL_BUG.md), [human-review scope](HUMAN_REVIEW.md).

The model adapter now accepts the current exact GPT-6 family plus Pro intelligence representation while keeping Parent Extra High requirements. Focused Bridge changes fix Pro final-content extraction, hidden-tab picker waits/cancellation, and the actual rich user-content reader without weakening exact Send checks. Future prompt templates request fenced JSON. All eight original patch files and prior research/approval data remain intact. Twelve accepted patches are packaged, with separate live/offline statuses. [Actual Pro evidence](PRO_UI_SELECTION.md), [patch/source integrity](release_readiness_before_final.json).

Explicit source-bound recovery uses exact request/conversation/user/final identities, complete terminal evidence and exact mathematical content. It commits through existing approval/P0 transactions and never rewrites the original failed turn or remote terminal. The historical Extra High-only tree's recovered pair is separate from the six new genuine-Pro pairs. [Parent recovery](PARENT_RECOVERY.md), [full live request/report chain](LIVE_RUN.md), [six-pair audit](six_pair_protocol_audit.json).

The final audit found that the experiment flushed older deferred report sections after its final updates. The harness now defers every section until the six-pair boundary and flushes by original insertion order. After a database backup, the ordinary section writer appended exact latest saved Root and spectral findings. Original section history, approvals, sessions, turns, rounds and Parent responses were preserved; an immediate repeat was idempotent. [Preserved stale report](report_publication_stale.md), [repair receipt](report_publication_repair_commit.json). Mathematical claims remain MODEL_PROPOSED, without independent verification.

## Verification and handoff

- **47 focused production regressions passed**, 6.684 seconds; Ruff passed. [Results](final_focused_tests.json).
- **41 focused upstream Bridge checks** and captured-DOM fixtures passed; pinned patch application/idempotence and deployed source hashes passed. [Bridge validation](user_payload_validation.json).
- **One additional experiment-only publication regression passed** in a temporary synthetic database, distinct from actual live evidence. [Validation](report_publication_offline_validation.json).
- Final exact roles passed at 10:11:35–40 UTC. The Bridge subsequently reported zero active requests, pending requests and pending commands. [Roles](final_role_verification.json), [idle state](final_runtime_idle.json).
- Original Chrome PID 8492, running since October 8, and the unrelated original tab remain preserved. Existing successful research tabs and pending-review pages stay open. [Browser preservation](final_browser_preservation.json).

**Human approval now verified:** at **8:21:26 a.m. PDT on October 15**, the user personally approved the N=4 audit prompt for **n-10712a75c7a1, round 1/version 1**, exact hash **1b9e4c081c99…**. The saved decision is HUMAN_APPROVED, and the real [dashboard](http://127.0.0.1:8767/) remains **已批准 / 等待调度** after refresh, with no pending popup. No repeated approval is needed. The project remains PAUSED with no worker, sessions or model turns, as stated in the approval request. The full genuine manual-review research cycle remains unverified. [Confirmed approval](human_approval_confirmed.json), [current interface](human_approval_confirmed.png).

No further manual extension Reload is needed. The latest supported maintenance reload returned HTTP 200 after all owned requests were terminal; the earlier timeout remains recorded separately. Unsettled historical work, optional unaided recall, live recursive promotion and the ninth live resume handler were not fabricated as passes.

## Clean source release

[Download source ZIP](../../dist/math-agent-consolidated-source.zip) — **60 files**, **184,840 bytes**, 12 accepted patch sets. CRC, duplicate-entry, exact-current-source and exclusion checks passed. No research databases, credentials, browser data, caches, virtual environments or upstream dependencies are included. [Package audit](final_source_package_audit.json).

SHA-256: `e6b28038dcff602e6de3007a81f8701ea5bc15c117d9e279423acda0e82c1789`.

The original `dist/math-agent-phase3-source.zip` is retained. Run instructions and precise limitations are included in the packaged `RELEASE_SUMMARY.md`. Actual private experiment evidence remains in this workspace.
