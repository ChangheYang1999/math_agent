# Exact Parent response recovery

Current checkpoint: **LIVE_PASS for two separate, exact source-bound local Parent recoveries**. The historical Extra High-only tree has one recovered pair and its sibling obligation remains pending. Separately, the new genuine-Pro tree recovered its elementary Leaf’s first Parent assessment after a natural Bridge deadline; the new tree subsequently completed all six genuine-Pro report/Parent pairs; see [LIVE_RUN.md](LIVE_RUN.md). Both original remote failures and local ERROR/null rows remain preserved. A committed recovery receipt does not retrospectively relabel either Bridge attempt as a successful terminal.

## Original evidence and current inspection

- Request: `mathagent_8dead57559845377aa96cac3e5f68d83`.
- Local turn: `parent:n-4360dde303ec-r000001:e0:a0`.
- Parent session: `S-69635a7172cd5208bd84c81f96463809`; client `extension:tab:1707788777`.
- Conversation: `6ad073a4-b6b0-83ea-8d27-eb898d8fc2c1`.
- Confirmed user-turn key: `c27f4451-1b2b-4d48-bbeb-3a35ee7daae0::user`.
- Input: **16,701 characters**, SHA-256 `bcc21af483ea8258fd188239ab8c7b5dc600182a41203dfbc3c846b066b60b48`.
- Observed assistant message: `68955394-7547-4acc-8cb7-c4d80c20ae82`.
- Historical candidate SHA-256: `00a8b4a7e53d3530d6e1d81f807ca777337732e59597cf79a05102285ab63cc3`; schema-valid next prompt: 4,946 characters.

The consolidated inspection used only exact-request GETs for the old bridge turn, its events and its items. [Fresh read-only evidence](old_parent_bridge_readonly.json) still reports a failed terminal, no output, and the same 136 request events. It does not provide a completed authoritative assistant reply. [Current DOM capture](old_parent_current_dom.json) provides additional current identity/content evidence; visual adjacency alone cannot release the obligation.

The original [halt checkpoint](../phase3/runs/live/halted_checkpoint.json), [candidate validation](../phase3/parent_candidate_validation.json), [historical live audit](../phase3/live_protocol_audit.json) and raw request evidence remain unchanged. The other accepted report, `n-952ae628fa68-r000001`, must retain its separate Parent assessment obligation.

## Missing proof and existing read-only history mechanism

Pinned upstream already provides optional source-bound conversation reconciliation through `/browser/recover-latest`. This command reads existing browser content/history; it does **not** submit an inference request. The exact supported body for this attempt is:

```json
{
  "sourceClientId": "extension:tab:1707788777",
  "index": 1,
  "reconcileConversation": {
    "conversationId": "6ad073a4-b6b0-83ea-8d27-eb898d8fc2c1",
    "userMessageId": "c27f4451-1b2b-4d48-bbeb-3a35ee7daae0",
    "assistantMessageId": "68955394-7547-4acc-8cb7-c4d80c20ae82"
  }
}
```

The pinned `conversationReconciliation.js` helper checks the exact selected conversation branch, assistant ID/role, nearest preceding user message ID, absence of a later superseding user/assistant message, final-recipient/channel, `finished_successfully`, `end_turn=true`, and full backend-text equality with the recovered visible answer. Positive evidence must report `matched_complete`, `exact_branch_boundary`, and `textMatches=true` for these exact IDs. Unknown schema, unavailable history, wrong branch, incomplete output or mismatching text remains blocking.

The upstream `TurnManager.recoverTurnFromLatestResponse` path is unsuitable here because it rewrites the old failed terminal to completed. This task instead preserves that terminal and its original local row.

Root executed the supported read-only command after extension reload and refresh of only the owned Parent tab. [Actual response](old_parent_source_reconciliation_after_reload.json): HTTP 200, correct persistent conversation, exact user/assistant turn keys, and the source-visible answer; however, `reconciliation.status=unavailable`, `reason=http_404`. An earlier request made while the extension was disconnected returned a preserved client-not-found error in [the first observation](old_parent_source_reconciliation.json). Neither is an inference or resend.

The current DOM candidate and recovered answer have different outer JSON formatting but exactly equal parsed fields, including every original mathematical string. `finishReason=recovered` means that text was retrieved; it is **not** proof of generation completion. The [read-only actual proof dry run](old_parent_recovery_dry_run.json) passed input/binding/JSON-equality checks and correctly refused recovery because the exact branch/assistant/terminal completion proof is still absent. Its [proof bundle](old_parent_proof_bundle.json) is preserved. No local commit or original-record change occurred. Further inspection must use an actually observed supported source; an endpoint must not be guessed merely to obtain a favorable result.

## Additional actual network proof

A later reload of only the owned Parent tab produced an actual successful history response. [Observed route metadata](old_parent_observed_history_routes.json) identifies network request `82230.1376`, HTTP 200, and the same conversation URL. [Captured response](old_parent_authenticated_history.json) retains the actual non-base64 response body. No request headers or authentication token were read or persisted. The earlier bridge `http_404` result is unchanged; no unsupported cause is inferred for that discrepancy.

The new pure `validate_history_capture(proof)` checks this independent authority directly rather than fabricating a successful Bridge reconciliation:

- The captured source, owned tab 1707788777, exact HTTPS origin/history URL, status 200, conversation ID and current branch match.
- The current final assistant message is `68955394-7547-4acc-8cb7-c4d80c20ae82`. Walking the actual ancestor pointers reaches the exact submitted user message `c27f4451-1b2b-4d48-bbeb-3a35ee7daae0`; intervening reasoning messages are not mistaken for the final answer. The complete backend user text has the original 16,701-character hash.
- Assistant status is `finished_successfully`, `end_turn=true`, recipient `all`, channel `final`, with `is_complete=true` and stop finish metadata. User and assistant share native request ID `dc8d0408-8349-4b04-8738-29e798dd1d79`.
- The record identifies model `gpt-6-thinking` and backend effort `max`; those are recorded as observed backend identifiers, alongside the original verified Extra High/xhigh UI evidence. No Pro result is claimed for this Parent.
- The actual text is wrapped in `<escape>...</escape>`. Its captured `model_dil_v2.constants["0"]` exactly reconstructs the entire original wrapper byte for byte. The validator reads this constant as data, executes no UI code, and performs no global unescaping of TeX or newlines. Decoded SHA-256 is `00a8b4a7e53d3530d6e1d81f807ca777337732e59597cf79a05102285ab63cc3`, identical to the current DOM candidate. Every parsed JSON value also matches the recovered text; only outer JSON formatting differs.

[Authenticated proof validation](old_parent_authenticated_validation.json) passed in SQLite `mode=ro`, with **no commit**. Its [complete proof bundle](old_parent_authenticated_proof_bundle.json) retains the positive network source and the unchanged unavailable Bridge evidence separately. Proof SHA-256: `7b4cea4953b6e2c3b4ba3f742d93d90867214fe4f70d9786f78dac9785d4fe6e`. At that snapshot, Parent response count remained zero and the original failed local row was unchanged. An explicit audited commit may now use this validated proof after its review.

## Actual audited commit and remaining obligation

After reviewing the positive proof, Root backed up the narrowly affected test database and executed the explicit commit at **2026-10-15 07:56:22 UTC**. This involved no Bridge or model request. [Commit evidence](old_parent_recovery_commit.json) records a second identical call returning `idempotent=true`.

The independent [before/after SQLite audit](old_parent_recovery_commit_audit.json) confirms:

- Parent pair count increased from **0 to 1**. Committed Parent payload SHA-256 is `f0933cfd845c54cc29f7b09b2d936b3bfc0aeaa9942d1c2569428568f3d477d7`, matching the receipt and validated source.
- Next round `n-4360dde303ec-r000002` is saved as **prompt version 2**, **14,895 characters**, `PROMPT_READY`, with the explicit `TEST_ONLY_EXTRA_HIGH_LEAF_OVERRIDE` notice. Its exact approval hash matches. Its `AUTO_APPROVED` gate follows this pre-existing review-OFF experiment's semantics; no human approval was invented.
- Stored report event **15** precedes Parent response event **25**, which precedes recovery receipt event **26**. There are **zero new Leaf dispatches**. The existing P0 transaction saved response and next prompt together.
- Every original turn row remains byte-identical, including the failed Parent's `ERROR`, null `raw_response`, request ID and original error. Existing error records remain unresolved and unchanged. The historical failed bridge terminal and `http_404` diagnostic remain preserved.
- The complete sibling round row remains byte-identical and `AWAITING_PARENT_RESPONSE`; it was not discarded or counted as completed. The historical halt manifest remains intact and no old automatic runner was restarted.

This result is a successful audited recovery of an existing real Extra High Parent answer. It is **not** a Pro inference result, a new six-pair experiment pass, or proof that the ninth patch's live `request.resume` handler ran. That handler's exact execution status is documented separately.

## New genuine-Pro tree: natural Parent deadline and audited recovery

This is a separate request and database from the historical case above. The live first elementary Pro report was already accepted; its mandatory Parent assessment was submitted once in the persistent Extra High Parent conversation.

| Identity | Actual value |
| --- | --- |
| Request / local turn | `mathagent_015a1cec9fa451cab8ea343ccdc4a6fb` / `parent:n-3790f8503746-r000001:e0:a0` |
| Owned source / conversation | `extension:tab:1707788883` / `6ad087b7-b0dc-83ea-82f2-b587762d8345` |
| Full immutable prompt | 15,576 characters; SHA `28a7492f1227cd53c04f61fa4c35fdd2358a640ec95fa35d7b28dd662312d898` |
| Recorded candidate user | `be1231b7-5dbc-4e6c-b0c9-a335af2fe993::user` |
| Actual current final assistant | `db982156-30ab-4d48-a87e-22f9d40d574d` |
| Native user/final request | `81743137-252c-4676-9c8f-246c3fe586e3` |

The [original terminal](new_parent_original_terminal.json) failed **naturally at 2026-10-15T09:09:21.425Z**, with `CANONICAL_DEADLINE_EXCEEDED` after 1,200,000 ms in preparing. A later interrupt request returned that already-failed terminal unchanged: [record](new_parent_wait_cancel.json). It was a no-op, not evidence that cancellation succeeded or stopped generation. The 457 [original events](new_parent_original_events.json) remain preserved. Normal GET-only `await_response` reconciliation then recorded the local ERROR and exact deadline code before the recovery backup; that fully failed row remains unchanged afterward.

No confirmed-Send diagnostic exists. The diagnostics instead show one submission effect/button attempt, full composer verification, baseline count 2 and a single candidate user at index 2. Initial rendered text was only 10,238 characters because the strict preview-prefix check did not expand Show more. After physical expansion, [actual payload](new_parent_expanded_user_payload.json) was 15,574 characters and exactly equal to the immutable raw prompt with only its two instruction backticks removed; [analysis](new_parent_expansion_analysis.json) preserves this distinction. The utility never normalizes that rendered loss into a claimed full-Send match.

The independently [observed owned-tab history](new_parent_authenticated_history.json) is HTTP 200 from the actual singular conversation route, network request `87267.6621`. Its exact current branch reaches the recorded user and preserves **all 15,576 raw prompt characters and their original hash**. The selected final has `finished_successfully`, `end_turn=true`, final/all, complete/stop metadata, actual model `gpt-6-thinking` and effort `max`. User and final share the native request above. The new submission authority is explicitly **AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT**, with **`confirmed_send_diagnostic=false`**.

The final’s known literal `<CodeBlock language="json" editable={false}>` wrapper is removed only by an exact round-trip check; no TeX, newlines or JSON string values are unescaped or normalized. Every parsed source field equals both the [fresh literal-code DOM](new_parent_completed_dom_after_reload.json) and the [earlier read-only recovered candidate](new_parent_source_candidate.json). The DOM also corroborates the exact final assistant and persistent conversation. The earlier candidate’s `finishReason=recovered` is not used as terminal proof. See [pure validation](new_parent_recovery_validation.json) and [complete proof](new_parent_recovery_proof.json).

Root committed the proven Parent response at **2026-10-15T09:16:39.326131Z** after its immediate backup. [Commit](new_parent_recovery_commit.json) records zero new inference requests and an idempotent repeat. Payload SHA is `421a2679b2c85116d2ef303dbac47f31867ba151f1faf5a740acfbe2f594b50b`; its exact 4,220-character next task was saved as `n-3790f8503746-r000002` with the ordinary review-OFF prompt gate. Optional schema defaults add empty proposal arrays and an empty independent-verification field; every supplied source string is preserved. This does not claim mathematical independent verification.

The separate [read-only commit audit](round1_recovery_commit_audit.json) confirms all original Parent-backup turn columns unchanged, the sibling recovered Pro report retained, exact source/receipt hashes, and mandatory event order **report 11 < Parent response 26 < next Leaf dispatch 29**. The sibling Pro report was separately recovered at 09:11:07 with its original ERROR/null source intact. At 09:16:52, an explicit zero-inference resume preserved immutable halt history and released only the two errors covered by exact committed receipts; all error source columns stayed unchanged and only their audited `resolved` flags changed. Further bounded work is reported in [LIVE_RUN.md](LIVE_RUN.md), not counted as part of this recovery action.

## Narrow local implementation

`src/math_research_agent/recovery.py` adds a pure proof validator and an explicit audited commit function. No automatic browser recovery or replay is added.

1. `validate_parent_recovery(store, turn_id, proof)` verifies the original error, exact parent/child/round/session binding, complete full-Send hash and length (or the separately recorded exact authenticated backend-user authority for the narrow natural-deadline path), current user/assistant identity, positive conversation-history completion/text evidence, and `ParentRoundResponse` IDs. It makes no external calls or state changes.
2. After a narrow project backup and explicit review of the proof bundle, `commit_parent_recovery(scheduler, turn_id, proof)` obtains the existing scheduler lock and uses the existing `_commit_parent` P0 transaction to store the response and concrete next prompt. It records full validation provenance and a committed recovery receipt in existing events. It never dispatches a Leaf or alters the original failed local/remote turn.
3. Pending-turn checks, tab-binding verification and pending-relay display now release an old failed Parent turn only when its exact original row hash, request/session/conversation/parent/child/round and the actual committed Parent response hash match the receipt. An unrelated failure stays blocking. A recovered old error cannot bypass normal checks that its tab is still on the bound conversation. No new database table, schema version or generic recovery framework is introduced.
4. A crash after Parent checkpoint persistence but before receipt persistence stays blocked. Repeating the explicit utility with the same proof is idempotent and completes only the audit receipt; it cannot send the old prompt again.

The original `ERROR`, error string, null `raw_response`, bridge request ID, prompt and source rows remain intact. The receipt records recovery separately rather than retrospectively relabeling the failed attempt a live success. Existing halt history must also be retained; continuation needs its own explicit, audited resume action.

## Validation and deployment status

[Offline validation](parent_recovery_offline_validation.json): the latest essential run was **35 checks passed in 4.69 seconds**, including two focused synthetic recovery cases; Ruff passed. Negative cases reject a wrong Send hash, wrong user/assistant/conversation, incomplete status, missing end-turn and mismatching text without mutation. Only outer JSON formatting may differ; any changed mathematical/string field is refused. The network fixture additionally refuses a different assistant, in-progress output and `end_turn=false`. The positive case accepts exact captured rich-text encoding while preserving the original Bridge `unavailable/http_404`, commits once, preserves the failed source byte-for-byte, saves an undispatched next prompt, preserves the other Leaf obligation, and then permits that separate mandatory Parent assessment without replaying the old request. It also checks that a changed browser conversation is rejected after recovery. A final focused recovery/bridge rerun passed **10 checks in 0.68 seconds**.

The current-DOM role fix and strict installation are documented separately in [PARENT_RECOVERY_BRIDGE.md](PARENT_RECOVERY_BRIDGE.md) and [bridge_install.json](bridge_install.json). The eight historical patch artifacts remain immutable. Source installation/fixture checks are distinct from live recovery inference validation.

Both actual commits used validated real source proof. No agent approval or synthetic response substituted for a model result. Further Leaf research remains undispatched in the historical old halted experiment; the new genuine-Pro project resumed through its own audited checkpoint. The latest shared recovery/tree/bridge regression after these narrow extensions passed 41 checks in 5.30 seconds; Ruff passed. These tests are offline and separate from the actual source-bound commits.
