# Parent recovery — bridge source and installation

This is the bridge source/deployment portion of the consolidated investigation.
Official Python reconciliation and any new live request are recorded separately
in `PARENT_RECOVERY.md`. No browser action, inference request or server restart
was performed by this source/install lane.

## Initial state and reproduced failure

The [initial read-only audit](bridge_initial_source.json) found pinned upstream
`0ffdae90239988f253058c05253226152acd55d2`, eight matching installed patch sets,
and zero active/pending requests or commands. The known Parent request
`mathagent_8dead57559845377aa96cac3e5f68d83` remained `ERROR`, with null local raw
response. The saved project had two reports, zero Parent responses and four
turns. This describes the initial snapshot, not any later audited recovery.

The legacy `requestResumeCommands.js` role lookup did not recognize current
keyed user/assistant wrappers. The actual current-turn helper did recognize
those same nodes. A projected boundary therefore falsely returned `missing`
with `userTurnCount=0`; the server then recorded
`CANONICAL_RECOVERY_UNCERTAIN`. The accepted three-line
`bridge/patches/resume_roles.patch` reuses the existing current-DOM role helper.
It does not change exact key/text matching, choose a different conversation,
weaken missing-boundary refusal, or send another prompt.

The focused `bridge/tests/resume_roles.mjs` fixture was rerun against the clean
managed checkout. It loads actual upstream DOM and resume code, reproduces the
before-fix missing-role result, and verifies after-fix exact user/assistant keys
and prompt text. Unrelated key/text remains missing; legacy matching and exact
text rebinding retain their previous behavior. Send calls remain zero.
Classification: **OFFLINE_PASS**. The separate shipped code-line fixture passed.

The [current live-DOM audit](current_dom_role_audit.json), based on Root's
07:40 UTC read-only capture of owned Parent tab 1707788777, confirms that this
repair fits the current page. The exact known user key has a
`group/user-message` / `data-chatgpt-search-message-ids` wrapper without legacy
role attributes. Its 16,701-character prompt has the original submitted hash.
The assistant retains the agent-turn-start marker and message ID
`68955394-7547-4acc-8cb7-c4d80c20ae82`. This supports the source diagnosis but is
not an authoritative acceptance of the candidate reply.

## Repeatable installation

The strict installer rejected the active temporary checkout because of a
previous one-line `package-lock.json` metadata change (`peer=true` for
`picomatch`). Its exact [bytes](bridge_package_lock_before.json) and
[diff](bridge_package_lock_before.diff) were backed up. That file and the old
server checkout were left unchanged; the installer was not weakened.

A clean persistent checkout was installed at
`~/.local/share/math-research-agent/chatgpt-bridge`. The unchanged
`scripts/setup_bridge.py` applied the nine reviewed patch sets and published
Extension 2.4.8 atomically to the already authorized directory
`/private/tmp/mathagent-live-extension`. The staged and publish runs both passed
`npm ci`, syntax/unresolved-identifier checks on 605 JavaScript files and the
340-file runtime package check. The repeated run and subsequent strict
`--check-only` verified all nine already applied.

[Installation evidence](bridge_install.json) records exact checks: all eighteen
reviewed source hashes and eleven installed extension hashes match. The eight
historical patch artifacts remain byte-identical. The old failed composer
candidate is absent. The ninth installed source SHA-256 is
`b4c0034347eff4fc3667bbc24535c977721c7e4ed18b1151ce5606271c31e9e5`.

The running server was not restarted: this ninth patch changes content code
only. Loading it requires the extension runtime and owned test pages to load the
installed source, with runtime/live evidence recorded separately. Installing files does
not by itself establish a loaded-runtime, live reattachment or accepted Parent
response. The old failure/candidate remain preserved until sufficient exact
source-bound evidence supports the separately audited recovery path.

The user subsequently reloaded the extension, and Root refreshed only owned
tabs 1707788871 and 1707788777. A
[read-only metadata snapshot](bridge_runtime_compact.json) at 07:45 UTC shows
both ready/compatible, extension 2.4.8, content 4.4.8, a fresh shared background
epoch and distinct content epochs. Both are idle without release pending.
The advertised bundle ID is a static upstream release identifier shared by
the eight- and nine-patch source; it does not cryptographically attest the new
patch. Exact installed source hashes, the user reload, owned-tab refreshes and
fresh metadata are separate operational evidence. This metadata read does not
prove the `request.resume` handler executed.

## Pro selection source observation

The existing power-slider reader can report the actual selected `Pro` tier.
Its opaque ID is `effort-pro-pro`; this is distinct from `xhigh`. No JavaScript
discovery patch is needed for that observed state. The pinned HTTP router has
only `GET /models` and `GET /efforts`, not model/effort selection routes. Its
internal `intelligence.apply` command is not HTTP-exposed, and the old selector
enumerates only the current observed power tier. Root uses the supported actual
mouse path in test-owned tabs and implements exact family-plus-tier verification
in Python; this source lane does not silently relabel Extra High as Pro.


## Consolidated continuation checkpoint

The source recipe now contains **eleven** exact-hash patch sets. The original
eight remain byte-identical, as do the ninth and tenth patch artifacts. The
additional eleventh `picker_activation` overlay activates only the connected
existing tab before model/effort reads and propagates the existing cancellation
signal through picker waits. No new HTTP route, tab creation, URL change,
cancellation registry or scheduler architecture was introduced. Its fixture and
26 focused upstream tests passed; exact managed/deployed hashes match.
[Eleventh installation](picker_activation_install.json),
[focused validation](picker_activation_validation.json).

Two user-confirmed extension reloads are recorded earlier in this investigation.
**There is no third user-confirmed reload.** The existing supported
`POST /browser/extension/reload` was attempted with owned Parent 1707788883,
`reloadTabs=false`, `allowMaintenancePageBootstrap=false`, and expected version
2.4.8 after aggregate Bridge idle was observed. It returned HTTP 500 with a
reconnect timeout at **08:47:36 UTC**. This is preserved as an unsuccessful API
result, not a reload pass or user confirmation.
[Exact response](eleventh_supported_reload.json). Root then refreshed only its
three idle experimental pages, never the original conversation or a new browser.
The subsequent six actual family/tier reads all passed at **08:48:28–08:48:32 UTC**:
Parent 8883 was GPT-6 / Extra High, and Leaves 8894 and 8897 were GPT-6 / Pro.
These are successful discovery observations, distinct from the maintenance
request's timeout and any full research-cycle outcome.
[Recorded checkpoints](first_pro_leaf2_failure_analysis.json).

The ninth `request.resume` role fix remains **offline verified and installed**;
its live handler execution remains **NOT_RUN**. The tenth selector has actual
read-only recovery evidence: it extracts the complete final reply rather than a
17-character reasoning recap. The first plain-Markdown reply still fails exact
mathematical-string fidelity, so its audited recovery uses authenticated canonical
final JSON and preserves the original `INVALID`/17-character terminal.
[Selector live read](final_answer_live_read_validation.json),
[known fidelity failure](final_answer_content_fidelity.json).

At this checkpoint the shared ledger reserves **4/16** new requests. Two distinct
actual Pro final messages are authenticated as `gpt-6-pro`; no Extra High result
has been relabeled as Pro. The second Pro reply used a fenced JSON block and its
Bridge read matched every canonical JSON field value exactly:
**LIVE_FENCED_CONTENT_PASS**. Its original upstream request nevertheless remains
failed with `CANONICAL_CONVERSATION_CHANGED`; output fidelity does not retroactively
make its submission evidence pass.
[Native final validation](leaf2_authenticated_validation.json),
[field-for-field fidelity](leaf2_fenced_output_fidelity.json).

That failure was caused by the newly added instruction's inline code delimiters
around the word json. The full composer and authenticated backend user message
retain 5,102 characters; the rendered user reader returns 5,100. Removing only
those two backticks reproduces its recorded text hash. With no established user
boundary, the existing guard refused temporary-to-persistent conversation promotion
on the same request. **The guard has not been weakened, and the prompt was not
resent.** Root corrected the nine future response templates to plain wording,
“single fenced JSON code block,” preserving fenced output without inline delimiters.
[Preserved original failure](first_pro_leaf2_failed_terminal.json),
[canonical timeline](first_pro_leaf2_failure_analysis.json).

This checkpoint does not claim all six new Leaf–Parent pairs, a manual-review-ON
Pro workflow, normal automatic recovery of uncertain submissions, or a third
user reload. Official recovery receipts and subsequent outcomes remain in the
separate research/recovery reports. No live mutation, UI action or inference was
performed by this source-audit lane.


The subsequent Parent prompt was also checked directly after expanding its own
Show more control. The complete displayed payload has **15,574** characters and
matches the immutable **15,576**-character input after removing only the same two
inline backticks. Embedded report mathematics, quotes and backslashes do not
require a new encoding layer. Before expansion, that early mismatch prevented
the existing strict prefix guard from clicking Show more; the larger apparent
loss was collapsed display, not discarded research evidence. Root's plain
“fenced JSON code block” wording is the focused future fix. No Unicode-encoding
helper, relaxed prefix check, weakened Send guard or automatic resend was added.
[Exact expansion comparison](new_parent_expansion_analysis.json).


At **09:29:34 UTC**, a separate new Round-2 attempt was explicitly acknowledged
as **FAILED_NOT_SENT** after its complete pre-dispatch busy-rejection evidence
was checked. Only that new local status changed; the original submitted error,
raw-null record, authenticated report receipt and upstream terminal remained
unchanged. The exact stale-lease release API had previously returned HTTP 202,
ambiguous, and was not retried.
[Actual acknowledgement](busy_acknowledgement_commit.json).

Root closed only the native-completed idle owned tab 8897, then used the existing
recover_session path to reopen the **same persistent conversation**
`6ad09396-818c-83ea-8252-bb2f31c6afee` in tab 9016 in the existing Chrome profile.
The logical session remains `S-d5870b32c59d57988c1b3f31b2e2c444`; only its browser
client binding changed. Exact Pro selection and all three role checks passed at
**09:29:55 UTC** before new dispatch. Closing/rebinding/verifying used zero model
requests and did not touch the original conversation or another node's active
request. The independent audit at **09:32:17 UTC** recorded **9/16** reservations,
two completed pairs and three accepted reports; subsequent inference remained
in progress. The planned total is 14 reservations, including the rejected attempt,
which was not refunded. This is audited recovery of one known-not-sent attempt,
not permission to retry an uncertain submission.
[Independent recovery audit](busy_recovery_readonly_audit.json).

The historical **09:27 UTC source checkpoint** passed **46 focused offline tests in 6.391 seconds**,
including exact busy-acknowledgement refusal cases and the immutable-receipt
checks. Its 58-file source review candidate contained the then-current source,
11 accepted patch sets and explicit fixtures, without runtime or private evidence.
Neither a candidate ZIP nor these distinct live checkpoints establishes that all
11 handlers ran live or that the bounded six-pair experiment has finished.
[Focused tests](final_focused_tests.json), [source candidate audit](release_candidate_audit.json).

At **09:45:56 UTC**, root published a twelfth four-line overlay to the same
managed checkout and extension folder. It selects the unique existing rich
user-payload root, excluding the new sibling ellipsis and Show more/less
controls. The captured Round-3 prompt has 19,178 exact characters; the old reader
returned 9,931 characters with interface text, while the corrected collapsed
root is a literal 9,918-character prefix. After one Show more action the offline
production-reader replay matches the full input and SHA-256 exactly. Wrong
prefixes, wrong tails, old turns and assistant turns remain refused. All
41 focused upstream regressions passed; all eleven earlier patch files remain
byte-identical. [Focused proof](user_payload_validation.json).

The first installer attempt failed because an explicitly named npm executable
did not exist. The normal pinned fallback then completed syntax checks for 605
JavaScript files, package checks for 340 files, and atomic publication. These are
file-install results. **No browser, server or extension reload was performed**;
the uncertain native-generating Leaf retained its existing document and content
runtime. Live execution of the twelfth fix remains **NOT_RUN**.
[Initial failure](user_payload_install.json),
[successful file publication](user_payload_install_retry.json).

The reconnect audit found no Send replay path for that exact uncertain
prompt.submit effect. A new document would, however, lose its unanchored
in-memory expected text and baseline, and canonical request.resume hydration
requires an already established submission boundary. Reload therefore is not
a proved recovery for this request. The current page is retained through native
completion and natural canonical terminal. Patch9 live handler execution is
still **NOT_RUN**. [Source call paths](pending_reload_source_audit.json).
The earlier 58-file review ZIP predates patch12 and its fixture; it is retained
as a historical candidate and must be rebuilt after the final live outcome.

The pending document was retained until its natural terminal at **09:53:24 UTC**.
After Bridge idle was confirmed, the supported maintenance update completed with
**HTTP 200 at 09:55:24 UTC**, and all three owned experiment clients were idle
and ready at 09:56:49. The first subsequent normal Parent request automatically
expanded its collapsed user turn and confirmed one Send with exact full
**19,116-character** input/hash at **09:58:37.990 UTC**. This is a live automatic
full-input delivery pass after patch12 deployment; it is distinct from the
offline rich-selector replay, the historical uncertain terminal, and final
research-cycle completion. Patch9's live request.resume execution remains
**NOT_RUN**. [Successful supported reload](twelfth_supported_reload.json),
[exact Send events](twelfth_first_live_send_events.json).

The subsequent normal Parent request `mathagent_0164b078f5f05b2985dfd64c1a31c40a`
also has captured actual rich-root proof: **23,768 characters**, exact reserved
input/hash, with the three historical literal containers separate. It expanded
its own **10,207-character** prefix at **10:00:49.186 UTC**, confirmed one Send
with the complete matching SHA-256 at **10:00:49.236 UTC**, and completed normally
at **10:02:56.085 UTC** with a 7,900-character reply. No mismatch event was
recorded. Patch12 therefore has **LIVE_RICH_PAYLOAD_DELIVERY_PASS**, independently
of the offline replay and without retroactively changing the old uncertain
terminal. Patch9 live handler status remains **NOT_RUN**.
[Full comparison](twelfth_live_rich_payload_validation.json),
[events](twelfth_rich_live_send_events.json),
[normal terminal](twelfth_rich_live_terminal.json).
