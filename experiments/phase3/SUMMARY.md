# Phase 3 results

Implementation is complete for review. **Production Pro remains BLOCKED; the bounded live experiment is LIVE_FAIL, with its state preserved.** No result below upgrades simulated transport into live inference. No human approval was performed by the agent.

## Outcome matrix

| Area | Verdict | Actual scope and evidence |
| --- | --- | --- |
| Exact GPT-6 Pro discovery | **BLOCKED / PRO_UNAVAILABLE** | Normal picker exposed enabled GPT-6 and GPT-5.6 Sol, with Extra High selected. No enabled exact Pro choice; zero Pro requests. [Discovery](PRO_MODEL_DISCOVERY.md). |
| Review popup, discussion, revision, refresh/restart | **LIVE_PASS — local UI only** | Actual Chrome dashboard; explicit offline provider. Two questions retained the same pending version; revision created version 2; restart restored the hash and history. [Human review](HUMAN_REVIEW.md). |
| Human approval | **WAITING_FOR_HUMAN** | Version 2 remains PENDING; zero Leaf turns. No approval button was clicked by the agent. [Final state](review_final.json). |
| Prompt/report gates and immutable correction workflow | **OFFLINE_PASS** | Actual HTTP routes with explicit synthetic decisions in temporary tests. Real Pro report gate remains BLOCKED. |
| Recursive splitting, allocation, safe pause/resume, meaningful communication, section ownership | **OFFLINE_PASS** | Two recursive depths, conserved weights, three useful leaves within capacity eight, zero-weight pause/resume, preserved history and independent coordinator binding. [Tree behavior](TREE_BEHAVIOR.md). |
| Live task decomposition and two research replies | **LIVE_PASS — Extra High override only** | Actual bootstrap plus two schema-valid Leaf reports, independent conversations, full Send hashes and authoritative terminal outputs. [Live run](LIVE_RUN.md). |
| Live generation concurrency | **LIVE_PASS — two Leaves** | 38.519 seconds of request-matched observed generation overlap; separate request-window overlap 85.094873459 seconds. This is not a three-node simultaneous generation claim. |
| Multi-round mandatory research cycle | **LIVE_FAIL / HALTED** | Four requests total: three completed; first Parent request failed after confirmed full Send. Two reports remain awaiting Parent, **0/6 completed pairs**, no round-two dispatch. |
| Phase 3 memory-recall probes and live recursive promotion | **NOT_RUN** | Halt occurred first. Persistent bindings alone are not claimed as memory verification. Prior Phase 2 memory results remain separate historical evidence. |
| Idle process restart | **LIVE_PASS — local recovery** | Separate runner processes preserved all saved identities and gates before Leaf dispatch; dashboard restart independently restored the pending review. |
| Current-DOM recovery role repair | **OFFLINE_PASS; live retest NOT_RUN** | Additional small `resume_roles.patch` reuses the existing role helper. Eight earlier patches are preserved. The installed runtime remains on those eight patches. |

## Focused changes

- Review ON now re-arms automatically approved gates that have not been crossed; queued local Leaf work rechecks its gate. In-progress Parent work remains preserved.
- Later/Escape deferral is page-local; the durable pending item can reappear after refresh. The modal includes a Chinese structural summary and an exact original-English link.
- Discussion replies receive a Chinese display translation while retaining authoritative English. Multiple questions do not approve or revise the artifact.
- Restored Parent history explicitly records whether a report was accepted and whether a response came from a human-requested correction.
- Optional internal communication no longer starves behind a paused, undispatched next prompt. Unconsumed reports and actual in-flight Leaf work still take priority.
- A new three-line bridge role fallback addresses the demonstrated false missing-boundary result on current ChatGPT markup. Exact request identity, prompt matching and fail-closed recovery are retained; no Send is added.
- The source packager accepts an explicit compact release summary, preserving the historical root `FIX_SUMMARY.md`.

The tree model, scheduler architecture, production roles, approval authority and mandatory Leaf–Parent loop were retained. New regression coverage consists of three review tests, one integrated tree scenario, and one targeted offline bridge fixture.

## Live failure and preserved state

Parent request `mathagent_8dead57559845377aa96cac3e5f68d83` submitted **16,701 characters** with exact expected/observed SHA-256 `bcc21af483ea8258fd188239ab8c7b5dc600182a41203dfbc3c846b066b60b48`. Its authoritative bridge terminal is `failed / CANONICAL_RECOVERY_UNCERTAIN`, and its local turn remains ERROR. No request was repeated and no later inference was sent. The phase used **4 of 16** allowed requests.

A later read-only browser observation found a schema-valid Parent reply adjacent to that exact rendered user prompt and turn key. It is saved as a **candidate**, not committed as a Parent response or used to authorize another round. [Candidate validation](parent_candidate_validation.json), [raw observation](parent_recovery_candidate.json), [live audit](live_protocol_audit.json), and [halted SQLite checkpoint](runs/live/halted_checkpoint.json) preserve both facts. The new repair was not deployed into the user's running browser and does not retroactively change the failed terminal.

The halted experiment's two reports and both Parent obligations remain durable. Formal report publication stayed behind the unsettled Parent checkpoint; no model proof was labeled independently verified. The live project has no running automatic scheduler. The separate local review server intentionally remains open behind its pending human gate.

## Validation and preservation

- **35 focused Python regression tests passed in 7.01 seconds**, including review, tree, Parent context and bridge transport. [Recorded result](final_tests.json).
- Focused source lint/format checks passed. The targeted bridge fixture, **23 focused upstream tests**, strict pinned installation and idempotent recheck passed; these are separate offline checks, not additional live calls. [Repair validation](resume_roles_validation.json).
- Existing eight patch bytes, production configuration, prior reports, historical research data and root `FIX_SUMMARY.md` were preserved. The manifest intentionally appends one separately identified offline repair; its original hash is retained in the baseline rather than rewritten. [Preservation and deployment audit](bridge_validation_final.json).
- The prior successful 20k prompt, multiline/TeX/code checks and three-session baseline were inspected and preserved, not rerun or relabeled as Phase 3 passes.
- [Cleanup](final_cleanup_compact.json) records zero active/pending bridge requests and pending commands, the original Chrome process and original unrelated tab preserved, and the intentional review handoff. The original ChatGPT conversation was neither read nor navigated.

## Source release and pending human action

The clean source package is [dist/math-agent-phase3-source.zip](../../dist/math-agent-phase3-source.zip). It contains application source, prompts, focused tests, the pinned installer, eight historical patches plus the new offline repair, and a compact release summary. It excludes credentials, browser data, environments, caches, project databases and large experiment evidence. Detailed evidence remains in this repository.

[Package audit](package_audit.json): **49 files, 135,984 bytes**, ZIP integrity and exact current source bytes verified. SHA-256: `1b6e1d32cd3f6570fb5064756153cfb3ba6851eb7e2c35f6823cc04a57c805ee`.

To continue the **offline review demonstration**, open [the local dashboard](http://127.0.0.1:8766/), review **prompt version 2** for node `n-4f28a4306033` (hash begins `1414a537c76f`), and click **批准此精确版本** only if you accept it. This is a simulated-provider item; it does not approve a Pro request or restart the halted live experiment.

Remaining blockers are exact Pro availability, genuine human approval, explicit reconciliation of the already-sent Parent request, and deployment/live validation of the new recovery repair. The incomplete three-round experiment and Phase 3 memory probes are not claimed complete.
