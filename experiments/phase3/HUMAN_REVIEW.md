# Phase 3 human review validation

The real local dashboard was exercised in the existing Chrome profile at `http://127.0.0.1:8766/`, using the isolated `human-review-offline` project. Its transport is explicitly **scripted/offline**: all Parent replies, revisions and translations in this exercise are simulated. This is evidence of actual dashboard interaction and durable workflow behavior, **not live GPT-6 Pro or Extra High inference**. No Approve button was clicked during this exercise. Human approval remains pending.

| Area | Verdict | Scope |
| --- | --- | --- |
| Visible modal, exact original link, Later/Escape, page refresh | LIVE_PASS — local UI only | Actual dashboard controls and browser display; simulated research transport |
| Two successive Ask Parent messages and revision | LIVE_PASS — local UI; OFFLINE_PASS — model transport | Actual UI actions; persistent simulated Parent session |
| Idle dashboard process restart | LIVE_PASS — local recovery | Same pending version, hash and discussion; all database tables unchanged |
| Prompt/report gates, stale approval rejection, immutable report correction | OFFLINE_PASS | Explicit synthetic actions in pytest temporary projects |
| Real Pro prompt/report approval path | BLOCKED | Exact Pro availability remains unverified/unavailable; no Pro inference performed |
| Genuine human approval | WAITING_FOR_HUMAN | Version 2 remains pending |
| Background notification delivery | NOT_RUN | Permission was `default`; no permission was requested |

## Actual dashboard observations

The project has one leaf, `n-4f28a4306033`, assigned to Parent `root`. The pending round is `n-4f28a4306033-r000001`. Manual review stayed ON and the project stayed ACTIVE. The durable round stage is `PROMPT_APPROVAL`, meaning it is awaiting prompt approval. There were **zero leaf turns in every saved observation**.

The real modal showed the leaf/parent IDs, round, a short Chinese summary, full English prompt, version/hash and separate Approve, Ask Parent, Request Revision and Later controls. Its original-English link returned bytes whose SHA-256 matched the pending content hash. The [version 2 screenshot](review_pending_v2.png) shows the modal and an offline demonstration banner behind it.

| Observation, UTC | Version / status | SHA-256 | Evidence |
| --- | --- | --- | --- |
| 2026-10-15 06:28:51.792333 | 1 / PENDING | `8ca30a186b4dc5dfdeb0a496555d6b8c6bab422baa11ebedd99282df235a99e5` | [Initial](review_initial.json) |
| 2026-10-15 06:29:48.356165 | 1 / PENDING after two questions | Same version 1 hash | [Two questions](review_two_questions.json) |
| 2026-10-15 06:31:00.348114 | 2 / PENDING after revision | `1414a537c76f2af560628f2e33dd66c8273f8b59258b4ed91d67ca7e213c2395` | [Revised](review_revised.json) |
| 2026-10-15 06:32:48.340645 | 2 / PENDING before restart | Same version 2 hash | [Before restart](review_before_restart.json) |
| 2026-10-15 06:33:52.148735 | 2 / PENDING after restart | Same version 2 hash | [After restart](review_after_restart.json) |

Later and Escape closed the modal without approval. Page reload restored the pending modal. The durable `deferred=1` flag retained the dismissal history but no longer suppressed future page loads. The inbox retained a visible pending count of 1.

Two Chinese questions were submitted using the actual Ask Parent control:

1. “请解释任务采用哪些假设。” — message `q-801e1f53cb77427b9d5c8cbab81f6eae`, completed at 06:29:12 UTC.
2. “这些假设为什么足够？” — message `q-6bc3f477c7f941f0a96367a16c17b33f`, completed at 06:29:37 UTC.

Their simulated discussion turns were `discussion:q-801e1f53cb77427b9d5c8cbab81f6eae:e0:a0` and `discussion:q-6bc3f477c7f941f0a96367a16c17b33f:e0:a0`. Both used the assigned persistent Parent session `S-6cb5c34734545de5bc6115b7eb053fac`, configured as GPT-6 Extra High. This is a **local simulated session identity**, with no browser conversation/client ID and no bridge request ID. It is not exact-model verification. The questions preserved the entire pending approval, round and Parent research state. Both replies and display translations completed, and neither action dispatched a leaf or created revision feedback.

The actual Request Revision control then submitted “请补充独立核查边界情况的步骤。”. Feedback `f-7d10ad5e50b4430e9396fe90ae516f72` completed through that same simulated Parent. It produced version 2 with a new hash and a fresh pending gate. Version 1 became SUPERSEDED; its original payload hash remains unchanged. Its two discussions remain in durable history, associated with version 1. Version 2 correctly starts a separate discussion thread rather than relabeling those older questions.

The generic fake translator explicitly returns a placeholder translation. These UI observations therefore do **not** establish faithful live translation or mathematical quality. Formula preservation was checked separately with explicit scripted translations in the offline HTTP tests. Research inputs/replies are English; Chinese originals and display replies remain confined to the user boundary.

## Restart and notification evidence

Only the test dashboard process, PID 82002, received SIGINT while the project was idle behind version 2's prompt gate. The [stop record](review_restart_stop.json) reports no model request in flight. The same project was restarted on port 8766; no approval or recovery bypass was performed.

The [read-only audit](review_ui_audit.json) compares the saved pre-restart SQLite backup with the current database, opened using SQLite `mode=ro`. All 15 application tables have identical contents and hashes, including two approvals/artifacts, two discussions, one revision feedback item, nine completed simulated turns and 12 events. Before/after dashboard snapshots also agree on nodes, rounds, approvals, sessions, turns, feedback, discussions and settings. There are no report or parent-response rows and no approved decision events.

[Notification inspection](notification_state.json) observed browser notification support, permission `default`, visible dashboard state and “审核收件箱 1”. No permission was requested and no background notification delivery was claimed. The persistent inbox and modal provide the fallback.

## Focused repairs and offline checks

- Enabling review now re-arms automatically approved prompts that have not dispatched and reports whose Parent consumer has not started. Existing Parent tasks/turns are conservatively preserved; uncertain browser work is never canceled or repeated. A locally queued leaf cannot bypass a newly re-armed prompt gate.
- Later/Escape deferral suppresses repeated popups within the current page; refreshing can surface the same durable pending item again.
- The modal adds a Chinese structural summary and a direct link to the exact original-English artifact.
- Parent discussion always receives an isolated Chinese display translation, with the authoritative English retained separately.
- Parent history restoration records `report_accepted` and `response_source`, preserving unapproved correction evidence without presenting it as an accepted result.

Three new meaningful tests in `tests/test_review_dashboard.py` cover these changes. One exercises the actual local HTTP routes with scripted transport: two questions, unchanged approval, durable history, prompt revision/stale rejection, a **synthetic** approval, report gating, and an immutable unaccepted report linked to a newly gated correction prompt. Separate existing tests check explicit report approval release and both review gates. No synthetic approval touched the running demonstration project or any existing research project.

The focused combined run passed **12 tests**, with 15 unrelated tests deselected; Ruff passed on the changed Python files. [JUnit output](offline_review_tests.xml) and [offline validation metadata](offline_review_validation.json) record the scope. These are OFFLINE_PASS results, not human approval or live Pro work.

## Pending human action

Open [the local dashboard](http://127.0.0.1:8766/), review **prompt version 2** for leaf `n-4f28a4306033`, and click **“批准此精确版本”** only if you accept that version. Its hash begins `1414a537c76f`; this approves an **isolated offline demonstration item**, not a real Pro request.

Until then, approval `n-4f28a4306033-r000001:prompt:2` remains PENDING with zero leaf turns. A genuine Pro turn/report gate cannot be validated while the exact required Pro model is unavailable; see [Pro discovery](PRO_MODEL_DISCOVERY.md). No human decision has been fabricated to cross that blocker.
