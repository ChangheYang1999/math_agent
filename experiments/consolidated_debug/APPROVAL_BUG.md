# Repeated-looking approval modal: diagnosis and repair

**Current status — October 15, 2026, 8:21:26 a.m. PDT:** the user personally approved the genuine-provider round-one/version-one prompt at port 8767. The exact hash `1b9e4c081c998f4d1bf9f67c6718a4f04e2b0178bce4a8d5b71931f18b7c8f71` is saved as APPROVED, with one `actor=human`, `source=HUMAN_APPROVED` decision. The real dashboard shows **已批准 / 等待调度** after refresh, zero pending reviews and no reopened popup. Project PAUSED, no scheduler worker, zero sessions and zero model turns. **No repeat approval is needed.** This is a genuine human Prompt-approval pass; the Pro turn, Report gate and complete manual cycle remain NOT_RUN. [Evidence](human_approval_confirmed.json), [refreshed interface](human_approval_confirmed.png). Earlier pending snapshots below precede this user action.

The user's approvals **succeeded**. Read-only inspection at **2026-10-15 07:35:33.692929 UTC** found that the original round-one prompt, version 2, had been APPROVED at **07:00:03 UTC**. The subsequent clicks approved **12 distinct artifacts** across six simulated research rounds. The pending item is now **round seven's prompt**, not the original version 2.

This corrects the interpretation of the older Phase 3 snapshot without changing that historical report. No recorded human approval was revoked, overwritten or recreated.

## Actual state and evidence

Project: `experiments/phase3/projects/human-review-offline`; leaf: `n-4f28a4306033`; Parent: `root`; manual review: ON; project: ACTIVE; provider: explicitly scripted/offline.

- Original artifact `n-4f28a4306033-r000001:prompt:2`, hash `1414a537c76f2af560628f2e33dd66c8273f8b59258b4ed91d67ca7e213c2395`: **APPROVED**, decision `approve`, at 07:00:03 UTC. Its round is RESPONDED.
- Six rounds each retain an approved prompt, immutable approved report, linked Parent response and saved next prompt. These mathematical replies were simulated, not GPT inference.
- Current pending artifact `n-4f28a4306033-r000007:prompt:1`, hash `0255039a5aefd7976724396ad700ecb131ec17fef5beba0401516fc976ae6030`: **PENDING**, round stage PROMPT_APPROVAL. No round-seven leaf turn exists.
- There are **zero `review_gate_rearmed` events**, zero unresolved errors and no failed local turns in this demo. No bridge inference request IDs are attached to its turns.

| Round | Prompt approved, UTC | Report approved, UTC | Saved Parent response |
| --- | --- | --- | --- |
| 1, prompt version 2 | 07:00:03 | 07:00:06 | Yes |
| 2 | 07:00:11 | 07:00:14 | Yes |
| 3 | 07:00:16 | 07:00:21 | Yes |
| 4 | 07:00:25 | 07:00:28 | Yes |
| 5 | 07:00:34 | 07:00:38 | Yes |
| 6 | 07:00:40 | 07:00:47 | Yes |

[Read-only DB/HTTP observation](approval_actual_before.json) contains the exact artifact IDs, hashes, decisions, events and round links. [The narrow pre-change SQLite backup](approval_demo_before.db) preserves the complete demo state. The source was opened in SQLite `mode=ro`; the backup copied into a new file. No SQL write or synthetic approval was applied to this project.

## Root cause

The interface immediately opened the next pending review after each successful click. Fake responses completed quickly. Consequently a prompt approval was followed almost immediately by its **report** approval, then by the **next round's prompt**. The report text and subsequent prompts were deliberately repetitive offline demonstrations. Their generic headings looked alike, while the changing round/version/hash was less prominent.

The old decision endpoint returned only `{ "ok": true }`. The UI closed the approved dialog, showed a generic toast and polled again; a new modal could cover the confirmation. It did not prominently distinguish “your previous item was approved” from “this is another artifact,” or show an approved-but-waiting-for-dispatch state. A delayed pre-click poll also lacked an explicit safeguard against redisplaying an artifact whose approval had just been acknowledged.

The saved events establish successful commits and advancement through distinct gates. They do **not** establish failed HTTP requests, rollback, accidental revocation or automatic rearming of the original artifact. The local server did not retain per-request access logs, so no historical HTTP status is invented. The diagnosis follows the durable decisions and exact round identities.

## Focused repair

The architecture and approval transactions remain intact:

- `/api/decision` now returns an authoritative receipt with exact artifact ID, type, round, version, hash, approval source and execution status. Duplicate approval requests return the same approved identity without creating another decision.
- Existing SQLite `APPROVED` plus `decision=approve` records remain unchanged. They are displayed explicitly as **HUMAN_APPROVED**. New decision events additionally retain `actor=human` and `source=HUMAN_APPROVED`; automatic approvals remain distinct. This is a compatibility display/source marker, not a retrospective approval action.
- The modal prominently displays artifact type, round number, version, complete ID/hash and queue position. A distinct next item names the previously approved artifact and explains that each report and prompt requires its own decision.
- Approval success closes that exact dialog immediately, with an identity-specific confirmation. A persistent “approved and waiting for execution” history distinguishes approval from model dispatch. Closure does not wait for inference.
- Submission disables the controls. A delayed stale poll cannot reopen the exact acknowledged ID/hash. Automatic modal advance is suppressed while an action is in flight.
- HTTP failures show their status and exact server explanation while retaining the unresolved item. A missing exact receipt is not presented as approval success.
- Existing review ON behavior still selects only eligible **AUTO_APPROVED** artifacts for rearming. Human-approved versions are never selected by that operation.

Changed application files: `dashboard.py`, `static/dashboard.html`, and the source fields in `Scheduler.decide`. No scheduler/tree rewrite, schema migration, history deletion or browser-model substitution was introduced.

## Validation

**OFFLINE_PASS:** one focused end-to-end regression runs the actual production dashboard JavaScript handlers/rendering against a real local HTTP server and SQLite database. Its DOM and model responses are explicitly simulated, and every synthetic approval is confined to pytest's temporary project. It reproduces the rapid prompt → report → next prompt sequence, completing two fake pairs with four **distinct** approvals.

The test checks in-flight disabling, exact receipt, immediate closure, APPROVED/WAITING_FOR_DISPATCH while the worker is paused, duplicate idempotence, stale polling, visible distinct queue identities, a visible HTTP 400 stale-hash error, preserved human approval across review OFF/ON, and refresh plus a fresh frontend/server instance restoring only the new pending artifact. Existing focused tests separately retain two Ask Parent messages without state changes and verify hash-specific revision and immutable report correction.

The focused suite passed **13 tests**, with 15 unrelated tests deselected, in 2.07 seconds. Ruff and the Node fixture syntax check passed. [JUnit](approval_tests.xml), [validation scope and source hashes](approval_validation.json). This is not a new genuine approval or a real ChatGPT inference claim.

## Actual repaired interface and restart

**LIVE_PASS — local dashboard only:** the root task stopped only its idle dashboard process, PID 82304, with SIGINT at **07:45:39 UTC**, then started a new process on port 8766. The pending item at that restart was round seven's prompt **version 1**. The [stop record](review_restart_stop.json) contains zero unresolved turns. [The actual Chrome screenshot](review_current_round7.png) shows that item alone, complete ID/hash and queue position, with an explicit notice that round six's report was already approved. The original round-one version 2 did not reopen.

Two further Ask Parent actions on round seven's version 1 completed through the same simulated Parent, retaining the gate and dispatching no Leaf. A separate Request Revision action created `n-4f28a4306033-r000007:prompt:2`; version 1 became SUPERSEDED. **The payload hash did not change:** the generic fake Parent returned exactly the same task text. A new version/approval ID still requires its own approval. This is a limitation of the scripted demonstration's content, not evidence of a changed mathematical prompt or of approval transfer. The custom offline test that changes prompt text separately verifies a changed hash.

Later closed the new modal; browser refresh restored only version 2. [Two-question display](review_two_questions.png), [version 2 display](review_revised_round7_v2.png), and [final UI/DB observation](review_after_ui_validation.json). A second server restart was not induced after version 2; the real process restart was tested on version 1 and the subsequent refresh on version 2.

[The independent read-only audit](approval_ui_audit.json) confirms every column of all 12 user-approved rows and all 12 approval decision events remains identical to the pre-change backup. The six completed simulated pairs and completed rounds also remain unchanged. The two new questions completed in the assigned Parent session; no round-seven Leaf turn or new genuine approval occurred. The current original-English endpoint returns the exact pending hash.

Latest saved state, **2026-10-15 07:54:06.421714 UTC**: round seven's **version 2 remains PENDING**, hash `0255039a5aefd7976724396ad700ecb131ec17fef5beba0401516fc976ae6030`. The repair does not require another click on the already-approved original round-one version 2. Round seven remains a **different**, durably pending review; it is not approved on the user's behalf. See [HUMAN_REVIEW.md](HUMAN_REVIEW.md) for the precise scope and optional next user action.

### Existing in-app dashboard deployment check

The user's already-open **in-app browser** dashboard tab still had the old JavaScript document, despite polling the updated backend. A server restart does not replace scripts already loaded into an open page. The root task verified the feedback field was empty, then reloaded **only this local dashboard page**. No approval was clicked and no typed draft was discarded.

[The refreshed in-app screenshot](review_iab_refreshed.png) now shows round seven/version 2, full artifact ID/hash, queue position 1/1 and the notice identifying the previously approved round-six report. This was a **stale frontend deployment**, not approval revocation. The page reload needed to expose the repair has already been performed. The final read-only DB recheck in [the audit](approval_ui_audit.json) again confirms the **12 genuine approved rows are unchanged, six simulated pairs remain saved, and the new round-seven/version-2 gate alone remains pending**. No source changes accompanied this check.

## Final approval-lane checkpoint

[Fresh read-only inspection](approval_final_readonly.json) at **2026-10-15 08:40:48.880974 UTC** again found exactly 12 approved rows, six simulated pairs and only round seven/version 2 pending. Canonical byte hashes for all approved rows and their original approval events match the pre-change baseline. The pending approval payload and saved round prompt both retain SHA-256 `0255039a5aefd7976724396ad700ecb131ec17fef5beba0401516fc976ae6030`.

The nine updated response templates now request fenced JSON for **future generated prompt versions**. They did not rewrite this existing pending prompt or transfer approval. The latest broad focused suite passed **47 tests in 6.684 seconds** at 09:59:10 UTC, with Ruff passing; these checks do not add human approval events. Earlier 42- and 45-test checkpoints remain historical evidence.

A separate genuine Pro smoke report was recovered at **08:23:53 UTC** into a **review-OFF** experiment and AUTO_APPROVED according to its existing mode. It is awaiting its mandatory Parent response. This is not human approval, a completed Parent pair, or a genuine manual-review-ON Pro workflow pass. That branch remains **NOT_RUN**.

The earlier third-manual-Reload request is no longer an external blocker. The supported maintenance API's HTTP 500/reconnection timeout remains preserved; refreshing only three idle owned experiment tabs then produced six successful model/effort reads and explicit continuation at **08:48:33 UTC**. No third user-confirmed click is claimed or needed. At the 09:09 UTC recovery checkpoint, four new requests are reserved and no new Parent pair is complete. [Latest independent approval check](approval_latest_readonly.json) still preserves the 12 genuine approvals, original approval-event hashes, six simulated pairs and the single pending round-seven/version-two gate. No approval action was performed.

A **separate real bridge-provider manual-review project** now exposes an actual pre-dispatch N=4 audit Prompt gate on port **8767**, with no scheduler worker, sessions or model requests. Root displayed [the real Chinese modal](genuine_review_pending.png) in Chrome without approving it. It is WAITING_FOR_HUMAN; this is not an additional approval or model result. Its version-1 item has a different node and hash (`n-10712a75c7a1`, `1b9e4c081c99…`); a 09:20:50 UTC read-only HTTP check still found PENDING and zero turns. See [HUMAN_REVIEW.md](HUMAN_REVIEW.md) for the single precise action. The original `8766` fake-provider gate and every genuine earlier approval remain separate and unchanged.

**Final review audit, 10:03:22 UTC:** [read-only SQLite evidence](final_review_readonly_audit.json) confirms the original project's 12 approved rows and 12 approval events retain their exact baseline hashes, with all six simulated pairs preserved. Only its separate round-seven/version-two candidate is pending. The real-provider port-8767 prompt remains PENDING with its exact version-1 hash, zero approvals/events, zero sessions, zero turns and zero reports. No further click has been attributed to the user and no automated approval occurred. This is the definitive approval-lane state; historical live-research request/pair checkpoints above are superseded independently by [LIVE_RUN.md](LIVE_RUN.md).
