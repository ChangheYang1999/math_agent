# Actual GPT-6 Pro selection

Selection verdict: **LIVE_PASS — actual Chrome picker**. Final inference outcome: **six genuine GPT-6 Pro reports and six saved Extra High Parent assessments**, across two persistent Leaves and three rounds each. The run ended with 14 reserved requests, including one proven not sent. Earlier capture failures and audited recoveries remain separately recorded below and in [LIVE_RUN.md](LIVE_RUN.md); selection alone is not used as inference proof.

The user was correct to distinguish the model family from the intelligence level. The current picker has a checked **GPT-6** family and a separate five-position intelligence slider. GPT-6 with Extra High and GPT-6 with Pro are different selections. The official [GPT-6 model guidance](https://help.openai.com/en/articles/20001354-gpt-6-and-other-models-in-chatgpt) describes Pro as using GPT-6 Pro/Astra when GPT-6 is selected; account eligibility still depends on actual access. No billing-plan inference was used.

## Actual mouse path

The existing Chrome browser/profile was reused. A new owned tab, **1707788871**, was opened at ChatGPT; no original conversation was read, navigated, refreshed or changed.

1. Captured the closed composer control: [closed view](pro_closed.png). It displayed Pro when the fresh page finished loading.
2. Physically clicked the intelligence control at `(1043,397)` to open its panel. The panel showed **Pro, 5 of 5**. [Opened panel](pro_picker_open.png).
3. Physically clicked the fourth slider position at `(1055,480)`, obtaining **Extra High, 4 of 5**, slider value 3. [Extra High](pro_path_xhigh.png).
4. Physically clicked the fifth position at `(1105,480)`, obtaining **Pro, 5 of 5**, slider value 4. It was selectable; no account lock, quota denial or upgrade flow appeared. [Pro selected](pro_selected.png).
5. Opened the panel's **Select model** submenu. **GPT-6 was checked**, while GPT-5.6 Sol was unchecked. No other model family was substituted.

These coordinates refer only to the captured viewport. The repeated setup sequence uses the actual visible picker in each owned tab, followed by source-bound verification; the application does not hardcode those coordinates. [Click/DOM evidence](pro_click_path.json).

## Adapter defect and focused repair

The bridge correctly reported the selected family as `GPT-6 / model-gpt-6` and the selected intelligence as `Pro / effort-pro-pro`, index 4. The effort ID is opaque; its observed label is the important Pro identity. [Raw bridge discovery](pro_bridge_before.json).

The Python adapter previously demanded a separate model radio labeled `GPT-6 Pro`. This representation did not match the current UI, even when Pro was selected. It now accepts exactly either:

- the older dedicated, exactly selected **GPT-6 Pro** model; or
- the current exactly selected **GPT-6** model **and** exactly selected **Pro** intelligence.

The default coordinator configuration `GPT-6 Thinking` also recognizes the observed GPT-6 family, while still requiring **Extra High**. Production configuration values remain unchanged. GPT-5.6 Sol with Pro, GPT-6 with Extra High masquerading as a Leaf, and a changed tier after Send are refused. A new focused synthetic HTTP regression checks these cases, including preservation of an unaccepted response after a post-Send tier change.

Actual inference submissions retain empty upstream fuzzy model/effort selectors and carry the exact verified family/tier in metadata. The current UI selection is re-read before dispatch and after a completed reply. The bridge does not expose a standalone HTTP intelligence-selection endpoint, so no endpoint was invented and no inference request was used merely to change selection.

## Repeatable node setup

For each fresh node: create/bind its dedicated persistent conversation; open the actual model/intelligence control; confirm GPT-6 in its family submenu; select Pro for a Leaf or Extra High for a coordinator; read the bridge's current family and tier in that exact client; send only after the strict role check succeeds; recheck after completion. A model name in the prompt cannot perform this transition.

The new genuine production-role experiment uses this procedure with independent node bindings. Its first Leaf report is the bounded Pro smoke and part of the six-pair target. See [LIVE_RUN.md](LIVE_RUN.md) for actual request IDs, terminal outcomes and stable conversation/tier evidence. No Extra High Leaf override is used in this experiment.

## Inference outcome

**LIVE_PASS — genuine Pro generation; LIVE_FAIL — initial Bridge answer capture.** Request `mathagent_91fd67634c1b5ff3b107263f1fc529c6` was sent once at 2026-10-15 08:05:16 UTC in Leaf tab 1707788894, conversation `6ad0893b-aed0-83ea-8da4-72db3bdec676`. Pre/post adapter verification recorded GPT-6 plus Pro. The actual completed history response, observed on that owned page at HTTP 200, identifies final assistant `dbd70ab8-6085-44dd-9919-c5837a2855dd` as `gpt-6-pro`, `finished_successfully`, `end_turn=true`, channel `final`, with a complete structured Leaf report. This independently confirms true Pro inference rather than merely a selected menu option. [Captured actual history](pro_smoke_authenticated_history.json).

The initial Bridge terminal incorrectly extracted the separate reasoning recap **“Worked for 5m 59s”** (17 characters). The local attempt is preserved as `INVALID`; no report or Parent pair was manufactured from that label. Further dispatch halted after two total new requests (bootstrap plus smoke). [Visible final response](pro_smoke_final_visible.png), [actual DOM structure](pro_smoke_full_turn_dom.json). At that checkpoint, the focused selector repair and source-bound recovery were pending; their later outcomes are recorded below. The original Leaf prompt will not be resent. This is not yet a production workflow pass.


## Actual recovery and output-format repair

At **2026-10-15 08:23:53 UTC**, the exact completed Pro final was committed through a narrow audited Leaf recovery after read-only proof validation and a fresh database backup. The stored report matches the authenticated final JSON, including every mathematical string. The original `INVALID` turn and its 17-character raw capture remain byte-identical; a repeated recovery was idempotent. No new model request occurred. The report is accepted under this disposable experiment's pre-existing review-OFF configuration and is **AWAITING_PARENT_RESPONSE**, with zero completed pairs at that checkpoint. [Commit](pro_smoke_leaf_recovery_commit.json), [independent audit](pro_smoke_leaf_recovery_commit_audit.json).

The tenth patch selects the actual assistant content instead of the reasoning recap. After the user's second extension reload, an actual read-only Bridge recovery returned the full final JSON. That proves live selector repair, but **not lossless Markdown reconstruction**: the web renderer had changed two underscore delimiters to emphasis, and the parser reconstructed stars. This difference remains explicitly recorded in [fidelity evidence](final_answer_content_fidelity.json). Canonical network text, rather than guessed normalization, supplied the recovery content.

Newly generated internal response instructions now require one fenced `json` block to protect literal strings from Markdown interpretation. The existing code-line patch and outer-fence schema extraction are retained. An essential synthetic Leaf→Parent regression preserves literal underscores, stars, TeX backslashes and newlines exactly. Existing stored prompts and approvals in previous projects remain untouched; the new experiment's unsent prompt can be revised only through its normal version/hash workflow.

Two zero-Send continuation checks encountered model-picker discovery timeouts after reload. Source and actual owned-client diagnostics show that the command arrived but hidden-tab picker waits stalled; a later foreground read returned GPT-6 plus Pro. This is a picker scheduling failure, **not evidence that Pro is unavailable**. A bounded activation/cancellation repair was then validated and installed. The two-request count describes that earlier checkpoint; the latest continuation is below.


## Post-installation discovery and second actual Pro final

There is **no third user-confirmed extension reload**. The supported maintenance
API returned HTTP 500, reconnect timeout, at **08:47:36 UTC** with only owned
Parent 8883 selected and broad tab reload/bootstrap disabled. Root subsequently
refreshed only the three existing idle experiment tabs. No original conversation
or replacement browser/tab was used.
[Retained API result](eleventh_supported_reload.json).

All six actual model/effort reads then passed between **08:48:28.898 and
08:48:32.995 UTC**: Parent 8883 had GPT-6 with Extra High; both Leaves 8894/8897
had GPT-6 with Pro, fifth slider level. This is a live discovery pass after the
installed activation/cancellation repair; it does not convert the earlier API
reconnect timeout into success. No further manual reload is established or
needed by this checkpoint.
[Actual recorded selections](first_pro_leaf2_failure_analysis.json).

The shared bounded ledger now contains **4/16** new requests. A second genuine
Pro Leaf request, `mathagent_4b6ed10cadb158698fb7fe1779f2b500`, generated a final
in owned conversation `6ad09396-818c-83ea-8252-bb2f31c6afee`. Authenticated current
final assistant `7b26a73d-7118-4609-9ecb-6c2ad3ec3662` is `gpt-6-pro`, channel
`final`, `finished_successfully`, `end_turn=true`. The complete authenticated
user text equals the original submitted 5,102-character input.
[Native validation](leaf2_authenticated_validation.json).

This second answer followed the fenced JSON requirement. Actual Bridge read-only
recovery matched **all JSON field values exactly**, including mathematical strings:
**LIVE_FENCED_CONTENT_PASS**. The earlier plain-Markdown underscore/star failure
remains in the record rather than being normalized away.
[Exact comparison](leaf2_fenced_output_fidelity.json).

The original second request still failed with
`CANONICAL_CONVERSATION_CHANGED`: Root's newly added phrase used two inline
backticks around json, which the rendered user message omitted. Its reader
therefore produced 5,100 characters and never established the exact submitted
user boundary before the normal temporary-to-persistent URL transition. The
existing guard refused the unanchored promotion. This is a submission-evidence
failure, **not wrong-model evidence or failure of Pro generation**.
[Preserved terminal](first_pro_leaf2_failed_terminal.json),
[hash/timeline diagnosis](first_pro_leaf2_failure_analysis.json).

Root has corrected all nine future templates to the plain wording “fenced JSON
code block.” Output fencing remains required; previously submitted input,
upstream errors and research records stay immutable. No uncertain prompt was
resent and no canonical boundary rule was relaxed. Fenced-output fidelity, actual
Pro generation, and complete automatic Leaf–Parent execution remain separate
verdicts; see the final live report for the latter.


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
It predates patch12 and is retained as a historical candidate.
Neither a candidate ZIP nor these distinct live checkpoints establishes that all
11 handlers ran live or that the bounded six-pair experiment has finished.
[Focused tests](final_focused_tests.json), [source candidate audit](release_candidate_audit.json).

At **09:55:24 UTC**, after the original uncertain Round-3 Leaf reached its
natural canonical terminal, the supported existing maintenance reload returned
**HTTP 200**. The precheck had zero active Bridge requests; it selected only the
owned Parent, disabled broad tab reload and maintenance-page bootstrap, and
reconnected with a new background/content epoch. The three owned experiment
clients were all idle and ready at **09:56:49 UTC**. This later successful result
does not replace the retained earlier eleventh-update HTTP 500.
[Supported reload](twelfth_supported_reload.json),
[idle runtime checkpoint](twelfth_runtime_idle.json).

The twelfth four-line overlay prefers the unique rich user-payload root and
excludes sibling Show more/less controls without weakening the complete-input
check. The first subsequent normal Parent request,
`mathagent_a6b666a4442b5c3db79c677f42bbd8a7`, automatically expanded its own
collapsed user message at **09:58:37.940 UTC**, then confirmed one Send attempt
with **19,116 expected and observed characters** and identical SHA-256
`2abaa9e959dd49c543bbb16bdc9e73a64d4cf174f2b93b3ef8c8fede7351cc37`.
The exact new user key was captured and the canonical prompt.sent event followed.
This is **LIVE_AUTOMATIC_FULL_PROMPT_PASS** after deployment. The saved events
do not identify which payload-selector branch was used; the captured rich-DOM
branch itself has the separate deterministic replay proof.
[Actual Send evidence](twelfth_first_live_send_events.json),
[rich-payload replay](user_payload_validation.json).

All twelve accepted patch files match their reviewed hashes; the original eight
and all eleven pre-existing overlays remain byte-identical. The ninth
request.resume handler still has **NOT_RUN** live status. The latest focused
source checks passed **47 tests in 6.684 seconds**, independently of the running
live experiment. At this source-audit checkpoint the shared ledger has **13/16**
reservations, and the remaining bounded jobs are still in progress; no six-pair completion
is claimed here. The prior 58-file source candidate is historical. The final
60-file source release must be rebuilt after the outcome is saved.
[Focused checks](final_focused_tests.json).

The next normal Parent request,
`mathagent_0164b078f5f05b2985dfd64c1a31c40a`, proves the new rich-container path
itself. Its actual captured user root contains **23,768 characters**, exactly
the reserved input with SHA-256
`36bbc4c418759d8488898ab4e49f6f0be8e14d934f405af3aecec08cccaa6346`;
the three older literal containers are separate. At **10:00:49.186 UTC**, the
bridge automatically expanded its own 10,207-character prefix. At
**10:00:49.236 UTC**, attempt1 confirmed the complete 23,768-character input and
same hash, with no mismatch events. The original request completed normally at
**10:02:56.085 UTC**, returning a 7,900-character answer. This establishes
**LIVE_RICH_PAYLOAD_DELIVERY_PASS** for patch12, without repairing or replaying
the earlier uncertain request. Patch9 live execution remains **NOT_RUN**.
[Rich-root comparison](twelfth_live_rich_payload_validation.json),
[actual events](twelfth_rich_live_send_events.json),
[original normal terminal](twelfth_rich_live_terminal.json).
