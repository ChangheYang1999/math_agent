# Consolidated human-review status

**Current status — October 15, 2026, 8:21:26 a.m. PDT:** the user personally approved the genuine-provider round-one/version-one prompt at port 8767. The exact hash `1b9e4c081c998f4d1bf9f67c6718a4f04e2b0178bce4a8d5b71931f18b7c8f71` is saved as APPROVED, with one `actor=human`, `source=HUMAN_APPROVED` decision. The real dashboard shows **已批准 / 等待调度** after refresh, zero pending reviews and no reopened popup. Project PAUSED, no scheduler worker, zero sessions and zero model turns. **No repeat approval is needed.** This is a genuine human Prompt-approval pass; the Pro turn, Report gate and complete manual cycle remain NOT_RUN. [Evidence](human_approval_confirmed.json), [refreshed interface](human_approval_confirmed.png). Earlier pending snapshots below precede this user action.

The user's subsequent clicks changed the saved Phase 3 demonstration after its historical report. They were genuine user actions according to the user's report, and the database retains **12 distinct `approve` decisions**: six prompt gates and six report gates. The original round-one prompt version 2 is approved, not pending. The repeated-looking popup was advancement to distinct artifacts, as documented in [APPROVAL_BUG.md](APPROVAL_BUG.md).

The provider for this project remains explicitly **offline/scripted**. Genuine user approvals in the local interface do not turn its simulated Leaf/Parent replies into GPT-6 Pro or Extra High inference.

## Current durable gates

Latest read-only observation: **2026-10-15 10:03:22 UTC**, both the original `8766` project and separate real-provider `8767` project. [Final audit](final_review_readonly_audit.json). Initial diagnosis at 07:35:33 UTC found the fake-provider round seven/version 1 pending; the authorized discussion/revision exercise produced version 2. The newer audit confirms its gate and every original human approval remain unchanged, while the separate real-provider gate below remains unapproved.

| Item | Actual state |
| --- | --- |
| Round one prompt version 2, hash `1414a537c76f…` | Human APPROVED at 07:00:03 UTC; original payload/history retained |
| Prompt and report gates, rounds one through six | Human approved; six simulated Parent pairs saved in order |
| Round seven prompt version 1 | SUPERSEDED by revision; never approved |
| Round seven prompt version 2 | PENDING / PROMPT_APPROVAL; no leaf dispatch |
| Current full approval ID | `n-4f28a4306033-r000007:prompt:2` |
| Current full hash | `0255039a5aefd7976724396ad700ecb131ec17fef5beba0401516fc976ae6030` |
| Manual review / project | ON / ACTIVE, gated |
| Agent approval actions on this project | Zero |
| Demo research errors or approval-rearm events | Zero |

The six complete simulated pairs demonstrate that the user's prompt approvals released a Leaf turn, each returned report waited for its own approval, the Parent response and next prompt were saved, and the next distinct prompt again required approval. The current pending seventh prompt cannot inherit any earlier human approval.

## Local interface and regression scope

The repair adds explicit full artifact identity and queue position, a prior-approved-item banner, authoritative approval receipts, persistent approved/execution history, disabled controls during submission and exact visible HTTP errors. Approval and dispatch remain separate states. The compatibility display calls existing `APPROVED` human decisions `HUMAN_APPROVED`; no old record is rewritten.

**OFFLINE_PASS:** the actual dashboard JavaScript, loopback HTTP routes and durable SQLite state were exercised using a minimal synthetic DOM, fake provider and explicitly synthetic approvals in temporary tests. The new regression reproduced rapid transitions between distinct prompt/report/next-round items and checked refresh and a fresh frontend/server instance. The combined focused suite passed **13 tests**. [Validation metadata](approval_validation.json), [JUnit](approval_tests.xml).

Repeated Ask Parent requests leave the approval, round and research state unchanged and use that leaf's assigned persistent Parent. A revision creates a new prompt version/hash; stale approval is rejected. Report correction preserves the original unapproved report and creates a separate linked task that requires prompt approval. These transitions remain separately verified offline; they are not claimed as new live model work.

The earlier [Phase 3 real-dashboard exercise](../phase3/HUMAN_REVIEW.md) remains historical evidence for actual Chinese modal display, two Chinese Ask Parent UI actions, a revision, Later/Escape, refresh and idle process restart with simulated transport. Its old “version 2 pending” snapshot is not reused as the current state. Background notification permission was not granted in that observation; no notification delivery is claimed.

## New actual Chrome and process-restart checks

**LIVE_PASS — local UI only:** after an idle SIGINT/restart of only the owned dashboard process, the actual Chrome page displayed the **round seven/version 1** item with complete identity, hash, queue position 1/1 and an explicit previous-approved-item notice naming round six's report. [Current-item screenshot](review_current_round7.png), [restart record](review_restart_stop.json). The original approved round-one version 2 did not appear in the pending queue; its historical HUMAN_APPROVED display remained available.

Two Ask Parent actions were then exercised through the real UI without any Approve action:

- `q-24a912b9dc604d57a408a9681375fa02`, completed **07:52:18 UTC**.
- `q-9546db416bac4a7f9f274f8903ca1bb7`, completed **07:52:33 UTC**.

Both refer to round seven's version 1 and the same hash. Both simulated discussion turns use the assigned persistent Parent session `S-6cb5c34734545de5bc6115b7eb053fac`; neither approved the item nor dispatched the Leaf. Chinese display and separately accessible English replies are visible in [the discussion screenshot](review_two_questions.png). Generic fake translations remain explicit placeholders, not live translation evidence.

An actual Request Revision action produced new approval ID `n-4f28a4306033-r000007:prompt:2`. The old candidate became SUPERSEDED. **Its hash remains the same** because the scripted Parent returned identical task text; no changed-content claim is made. The independent version/approval identity still enforces a fresh gate. Offline custom scripts separately demonstrate that changed text produces a changed hash. No code rewrite is warranted simply to manufacture a different fake task.

Later closed the version 2 popup and page refresh restored it. [Version 2 screenshot](review_revised_round7_v2.png), [final saved state](review_after_ui_validation.json). The real server restart was performed at version 1; version 2 was subsequently refresh-tested, without an additional server restart.

[Independent read-only audit](approval_ui_audit.json) verifies all 12 pre-existing genuine approval rows and all 12 corresponding decision events are unchanged in every column. All six earlier simulated pairs remain unchanged, exactly two new discussions completed, no round-seven Leaf turn exists, and no new genuine approval event was added. The original-English endpoint returned all 3,896 bytes with the exact pending SHA-256. No actual Approve control was used by automation.

A production GPT-6 Pro prompt/report approval path requires separately verified Pro selection and an actual Pro turn; this simulated demo does not establish that result. See [Pro selection](PRO_UI_SELECTION.md) for the independent model investigation.

The root task also checked the user's **existing in-app browser dashboard tab**, which had retained the older JavaScript while polling the current backend. After verifying the feedback field was empty, it reloaded only this local dashboard. [The refreshed display](review_iab_refreshed.png) shows the updated round-seven/version-2 identity, complete hash, queue 1/1 and previous-approved-report notice. This deployment refresh did not approve anything or revoke any earlier approval. A fresh read-only DB comparison again preserved all **12 genuine approval rows and six fake-provider pairs**; the same new version 2 remains pending. [Audit entry](approval_ui_audit.json). No source was changed for this final display check.

## Genuine Pro result and remaining review scope

The separate genuine Pro smoke completed remotely and its exact final report was recovered at **2026-10-15 08:23:53 UTC**. That disposable project already had manual review **OFF**. Its ordinary AUTO_APPROVED report is accepted and `AWAITING_PARENT_RESPONSE`, with **zero completed Parent pairs** at the 09:09 UTC recovery checkpoint. The original failed extraction/INVALID turn remains preserved. [Source-bound commit audit](pro_smoke_leaf_recovery_commit_audit.json).

This recovery is neither a human decision nor a manual-review-ON Pro exercise. **The genuine-provider Prompt gate is now WAITING_FOR_HUMAN in a separate project described below; its Pro turn, Report gate and completed manual-review-ON cycle remain NOT_RUN.** The real user approved the earlier fake-provider demonstration; no subsequent genuine Pro prompt/report approval has been fabricated. The automatic-mode experiment's four-request checkpoint and planned six-pair path are separate from this zero-request review handoff.

The nine source response templates now request one fenced JSON block to preserve literal mathematical strings. These instructions affect future generated prompt versions only. [Final read-only verification](approval_final_readonly.json) checks that this demonstration's existing pending payload and round prompt still have their original hash, and all 12 user-approved rows/events retain their baseline byte hashes.

The latest broad focused run passed **47 tests in 6.684 seconds** at **09:59:10 UTC**; Ruff passed. [Final test record](final_focused_tests.json), [JUnit](final_focused_tests.xml). They remain offline regressions, not additional user approvals, model inference or a completed manual Pro cycle. Earlier 42- and 45-test runs are historical validation, not the latest total.

## Genuine bridge-provider Prompt gate: WAITING_FOR_HUMAN

A separate disposable project at `runs/human_review/project` now uses the **real bridge provider**, manual review ON and unchanged production Pro/Extra High roles. Its one meaningful task independently audits the **N=4** cyclic mean-zero Poincare inequality, sharpness, equality vectors and exact stability defect by elementary algebra and a matrix cross-check. The operator-prepared initial candidate references the two actual stored Pro reports and labels their claims model-proposed rather than independently verified. It is not a simulated response or a claim that this new project's Parent has already generated the prompt.

The ordinary Store initialization/split methods created one active Leaf within capacity one and the ordinary durable Prompt gate. **No inference, session creation/binding, discussion, report, Parent response or approval occurred.** The project is PAUSED and is served at [127.0.0.1:8767](http://127.0.0.1:8767/) using the existing `Dashboard.handle` endpoints with **no scheduler worker**. The small experiment launcher adds no production abstraction. Cached bridge health is intentionally undiagnosed in this server; this is not evidence of model unavailability.

| Exact item | State |
| --- | --- |
| Leaf | `n-10712a75c7a1` |
| Round | `n-10712a75c7a1-r000001` |
| Prompt / approval | Version 1 / `n-10712a75c7a1-r000001:prompt:1` |
| SHA-256 | `1b9e4c081c998f4d1bf9f67c6718a4f04e2b0178bce4a8d5b71931f18b7c8f71` |
| Gate | PENDING / PROMPT_APPROVAL |
| Web model calls / sessions / human approvals | 0 / 0 / 0 |
| Dashboard process | PID 92974; port 8767; no scheduler worker |

The original-English route returned all **5,480 characters** with the exact pending hash. [Prepared gate evidence](human_review_pending_prompt.json), [actual local HTTP state](human_review_http_state.json), [minimal handoff launcher](serve_human_review.py). This establishes a real-provider **pre-dispatch gate**, not a completed genuine Pro manual-review workflow.

**LIVE_PASS — local UI; WAITING_FOR_HUMAN — genuine-provider Prompt gate:** Root displayed the actual Chinese modal in an owned Chrome tab. [Actual screenshot](genuine_review_pending.png) shows round 1/version 1, the full node/approval/hash, queue 1/1, English original link and separate review controls. [UI evidence](human_review_ui_validation.json). No Approve control was used by automation. The user was asked to inspect and personally approve the exact candidate if accepted. A read-only HTTP check at **09:20:50 UTC** still found this version PENDING, zero bound sessions, zero turns and no approval history. The ordinary dashboard backend will persist a user's eventual exact approval as APPROVED/WAITING_FOR_DISPATCH; this idle server cannot automatically send it to a model. No actual Pro session or Pro response is claimed for this project.

The **10:03:22 UTC final read-only audit** still finds exactly this PENDING version/hash, zero approvals, zero approval events, zero sessions, zero turns, zero reports and zero completed pairs in the real-provider handoff. It also reconfirms every column of the original fake-provider project's 12 human approvals and 12 approval events through their unchanged baseline hashes, six saved simulated pairs and its separate round-seven/version-two gate. The advancing review-OFF research experiment is independent; its latest inference outcome belongs in [LIVE_RUN.md](LIVE_RUN.md), not a claim that this manual gate has been crossed.

**One requested human action:** open [the real-provider review dashboard](http://127.0.0.1:8767/), review the **N=4 audit prompt version 1** for `n-10712a75c7a1` (hash begins `1b9e4c081c99`), and click **“批准此精确版本” only if you accept it**. This approves the proposed prompt; it does not claim that a model has run. Subsequent session/model setup, genuine Parent discussion, Pro report approval and the full manual cycle remain NOT_RUN.

The old `8766` fake-provider project is separate and untouched. Its 12 genuine user approvals and six simulated pairs remain preserved; its optional round-seven/version-two candidate is still pending, ID `n-4f28a4306033-r000007:prompt:2`, hash beginning `0255039a5aef`. **No further approval is needed to confirm that the original round-one version 2 succeeded.**

The earlier request for a third manual extension Reload is **resolved without requiring another user click**. The supported maintenance attempt returned HTTP 500/reconnection timeout, which remains preserved in [its record](eleventh_supported_reload.json). The root task refreshed only three idle owned experiment tabs; all six model/effort reads succeeded, and explicit continuation resumed at **08:48:33 UTC**. No third user-confirmed Reload is claimed. The new human action above concerns only the separate real-provider Prompt gate. [Read-only preservation evidence](approval_latest_readonly.json) records the unchanged `8766` project.

Final handoff check at **10:15:27 UTC** retains the same pending 8767 version/hash and zero approvals/turns/pairs. Every one of the original 8766 approval rows and decision events still equals the pre-change backup. [Final handoff evidence](handoff_review_state_final.json), [current actual modal](genuine_review_pending_final.png). The separate review-OFF experiment has now completed six genuine-Pro pairs; this does not cross the human gate.
