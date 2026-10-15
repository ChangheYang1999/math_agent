# Long-prompt fix summary

State: **direct long-input LIVE_PASS; tree 4/4 LIVE_PASS; final math/code LIVE_PASS; exact Pro BLOCKED**. See [RESULTS_LONG_PROMPT_FIX.md](RESULTS_LONG_PROMPT_FIX.md) for exact identities, timestamps, hashes and failure records. The earlier RESULTS.md and failed candidate evidence remain unchanged.

## Confirmed result

A real **20,236-character** prompt completed through the existing Chrome profile with exact GPT-6 / Extra High (`xhigh`) verification before and after. Requested and fully submitted SHA-256 matched, exactly one Send and one own-turn expansion were recorded, and the authoritative terminal reply returned both markers, `1591` and final reference `0140`.

- Request: `mathagent_a91d1285a2885750b9f3288af583d3ae`.
- Conversation: `6ad023ba-7000-83ea-aba3-e98fcd4bdc9c`; client `extension:tab:1707788760`.
- SHA-256: `bfb9e658cbc4ff0631b325a8afa7cebcfef4926f6a404929a10e443b052add9e`.
- Remote completed: 2026-10-15 00:52:16.645 UTC; locally verified: 00:52:18.268 UTC.
- [Authoritative evidence](runs/20261015-long-prompt/evidence/direct-long20k.json).

The distinct 16,198- and 19,660-character diagnostic requests were actually sent and replied in the browser, but failed authoritative reconciliation. They were interrupted, retained and never resent or marked not sent. Their UI replies do not count as terminal passes. The 655-character baseline passed after an earlier positively proven pre-Send failure.

## Changed boundaries

| Files | Purpose |
| --- | --- |
| Upstream `content/composerCommands.js`, `artifactCaptureMain.js` | Correct MAIN/content message-channel mismatch; native literal multiline span/BR insertion; complete editor/user-text verification; scoped pasted-text and collapsed-user expansion; hashes and bounded fresh-DOM confirmation. |
| Upstream `content/requestEffectReconciliation.js`, `src/bridge/state/requestEffectTransitions.js` | Keep post-Send ambiguity uncertain; prevent automatic submission replay; terminal-fail only exact positive preparation cancellation proof. |
| Upstream `src/bridge/coordinator/bridgeClientEventRouter.js`, `requestResultMaterializer.js`, `src/turnManager.js` | Preserve positive cancellation fields through authoritative events and durable turn errors. |
| Upstream `content/requestMonitor.js`, `userTurnState.js`, `turnSnapshots.js` | Adopt a delayed full new user turn from the original in-memory baseline, excluding Show more/less UI; bind its existing assistant without Send. Does not establish baseline persistence across document reload. |
| Upstream `responseParserCore.js`, incremental `content/responseDom.js` overlay | Preserve observed CodeMirror line boundaries, indentation and blank lines; retain TeX handling and literal code. |
| `src/math_research_agent/bridge_transport.py`, focused bridge tests | Explicit proof-checked not-submitted acknowledgement; uncertain/sent requests remain blocked. No automatic new request. |
| `src/math_research_agent/parent_prompt.py`, scheduler prompt assembly, Parent prompt text/tests | Remove repeated old evidence and schema decoration while retaining the complete new report/evidence, IDs, constraints, context restoration and Python validation. |
| `audit_historical_parent_retry.py` | Disposable-only, explicit e3 acknowledgement and epoch 3→4 with immutable audit/backup; standard recovery cannot dispatch. No generic interrupted-turn bypass. |
| `bridge/`, `scripts/setup_bridge.py` | Eight accepted patch sets in a pinned manifest; checksum/revision refusal, clean-checkout application and idempotent rerun verified. |

## Accepted and rejected evidence

- Retained: exact picker/effort, temporary conversation identity, release-handshake settlement and math extraction patches. Their previous live evidence is preserved.
- Additional accepted sets: [corrected composer](upstream_long_prompt_v2.patch), [delivery state](upstream_delivery_state.patch), [observation recovery](upstream_observation_recovery.patch), and [code lines](upstream_code_lines.patch). [Final installer verification](setup_verification_final.json) confirms eight sets and exact final source hashes.
- Rejected historical candidate: [upstream_composer.patch](upstream_composer.patch), still separately labeled [UNRESOLVED / NOT_APPLIED](composer_fix_status.json). Passing synthetic fixtures did not make its failed live behavior a success.
- The old internal Show-control discrepancy remains unexplained. The verified new defects are the channel mismatch, multiline serialization, collapsed user payload and stale confirmation observation. No opacity/race cause is invented for the earlier discrepancy.

## Parent/tree invariants

The same saved second-round Parent case shrank from **13,065 to 10,988 characters (15.897%)** while retaining the entire new report and its 3,491-character proof. [Exact comparison](parent_prompt_comparison.json) records equal report/evidence hashes. The independent direct 20k pass establishes transport capability beyond that optimization.

Historical e3 recovery [applied with zero prompts](runs/20261015-long-prompt/historical_e3_verified_20261015T005023993578Z.result.json). Four complete Leaf reports and the original two Parent responses were preserved. The two saved second-round reports now have completed Parent responses, reaching **4/4 validated pairs** in the original Parent conversation. Actual new inputs were **10,988 and 18,008 characters**, with full submitted hashes and exact GPT-6/xhigh checks before and after. The [final tree audit](runs/20261015-long-prompt/tree_final_audit.json) verifies unchanged report bytes, exact links, protocol ordering and no new leaf turns. The two saved round-3 prompts contain 2,655/3,590 characters and remain undispatched.

Production leaves remain GPT-6 Pro, internal nodes Extra High, with human gates unchanged. [Actual picker evidence](runs/20261015-long-prompt/pro_availability.json) contains no exact GPT-6 Pro option, so the optional Pro check is **BLOCKED with zero inference requests**. Disposable Extra High leaves are not a Pro pass. Capacity remains a maximum; optional messages and tree weights retain their semantics.

## Validation and remaining finalization

Focused Python checks: **36 passed in 3.91 seconds**. Separate upstream groups passed **14 selector/request-machine**, **34 interaction/reconciliation**, **9 observation**, and **5 DOM/parser** checks. Paired-world multiline/hash/uncertainty, explicit cancellation propagation, immutable identity reuse, same-request observation and retained math/code fixtures are saved separately as offline validation. They are never counted as live inference.

The first [live math/code record](runs/20261015-long-prompt/evidence/direct-math-code.json) completed and preserved radicals, fractions, subscripts and powers, but merged the two CodeMirror code lines. It remains **LIVE_FAIL for code extraction**. The [first read-only snapshot](runs/20261015-long-prompt/math_code_readonly_recovery.json) also failed before the updated extension loaded; the [final read-only snapshot](runs/20261015-long-prompt/math_code_readonly_recovery_final.json) preserved the exact formula and both code lines. Neither snapshot is new inference or a replacement terminal.

The distinct [final live turn](runs/20261015-long-prompt/evidence/direct-math-code-final.json), `mathagent_5c10db4e14845c5ebe972b6a5dec88a3`, is **LIVE_PASS**: full submitted hash for all 293 input characters, exact GPT-6/xhigh before/after, authoritative completion at **00:59:29.928 UTC**, exact TeX and two-line Python fence, with new markers 428/795. The earlier failure remains intact.

The [final cleanup](runs/20261015-long-prompt/final_cleanup_long_prompt.json) records all drivers stopped and zero active/pending requests or commands. The local bridge remains on 127.0.0.1:8080. The same Chrome process/profile and untouched original tab remain; four result tabs were kept, only three disposable diagnostic tabs closed. All 22 baseline evidence hashes are unchanged.

Source-only archive: `dist/math-agent-long-prompt-fix.zip` (**inspection PASS**). It contains the project source, focused tests, eight accepted pinned patch sets, the shipped code-line fixture, and this compact summary. Credentials, research databases, detailed live evidence, environments, caches, historical copies, and third-party dependencies are excluded. The archive checksum is recorded separately in `package_validation.json`, avoiding a self-referential packaged hash. Installation, inference and cleanup evidence remain separate; the earlier baseline cleanup is not used to claim this run's final state.
