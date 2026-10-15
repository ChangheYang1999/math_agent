# Long-prompt delivery continuation

Updated from saved evidence on **2026-10-15 UTC**. Direct long input, the four-pair tree continuation and the distinct final math/code turn are **LIVE_PASS**. Exact GPT-6 Pro is **BLOCKED** by the observed picker. The earlier [RESULTS.md](RESULTS.md) is preserved unchanged.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Three concurrent GPT-6 / Extra High conversations | **LIVE_PASS — referenced baseline; not rerun** | [Prior report](RESULTS.md), [tree audit](tree_audit.json) |
| Short multiline baseline, 655 characters | **LIVE_PASS** after one positively not-sent failure | [Completed short turn](runs/20261015-long-prompt/evidence/direct-short-e1.json) |
| Direct 16,198-character diagnostic | **LIVE_FAIL** for terminal reconciliation; known submitted, explicitly interrupted, never resent | [Original turn](runs/20261015-long-prompt/evidence/direct-long-16000.json), [read-only full DOM evidence](runs/20261015-long-prompt/long16_diagnostic_preserved.json) |
| Distinct 19,660-character diagnostic | **LIVE_FAIL** for terminal reconciliation; known submitted, explicitly interrupted, never resent | [Original turn](runs/20261015-long-prompt/evidence/direct-long19k.json), [full DOM evidence](runs/20261015-long-prompt/long19_diagnostic_preserved.json) |
| Distinct 20,236-character direct check | **LIVE_PASS** — full submitted hash, one Send, authoritative completed reply | [Completed long turn](runs/20261015-long-prompt/evidence/direct-long20k.json) |
| Four saved Leaf Report → Parent Response pairs | **LIVE_PASS — 4/4**, four original reports unchanged, no additional leaf inference | [Final tree audit](runs/20261015-long-prompt/tree_final_audit.json), [tree summary](runs/20261015-long-prompt/tree_summary.json) |
| Actual GPT-6 Pro leaf smoke | **BLOCKED — zero Pro inference requests** | [Exact picker evidence](runs/20261015-long-prompt/pro_availability.json) |
| Live math/fenced-code continuation check | Distinct final turn **LIVE_PASS**; first terminal **LIVE_FAIL** remains preserved | [Final completed turn](runs/20261015-long-prompt/evidence/direct-math-code-final.json), [first terminal](runs/20261015-long-prompt/evidence/direct-math-code.json) |

All inference used the existing Chrome instance and logged-in profile through the third-party browser bridge, not API inference. The exact observed model label is **GPT-6** (`model-gpt-6`), effort **Extra High** (`xhigh`). This does not establish a GPT-6 Pro pass. Production leaf defaults remain GPT-6 Pro; Extra High leaves are a disposable experiment override.

The referenced baseline's actual three-way generation overlap was **8.029 seconds**. Its **16.1975-second** shared request-inflight interval is a different measurement. Neither was rerun or used as evidence for the new long-input turn.

## Confirmed long-input result

The successful direct payload was **20,236 characters**, larger than the original 13,065-character failure and independent of Parent prompt optimization. Its requested and observed submitted SHA-256 are both:

```text
bfb9e658cbc4ff0631b325a8afa7cebcfef4926f6a404929a10e443b052add9e
```

Request `mathagent_a91d1285a2885750b9f3288af583d3ae` used client `extension:tab:1707788760`, persistent conversation `6ad023ba-7000-83ea-aba3-e98fcd4bdc9c`. Exact GPT-6/xhigh checks passed before and after the turn. The full new user-turn key was `be14b16c-d4b5-4cd4-ad0b-b132d194f3a3::user`.

Saved events show:

- MAIN-world `insertHTML` preparation, exact logical text length 20,236, and **143 expected/observed newlines**, with no first mismatch.
- One `diagnostic.send_button.found` event, one automatic `prompt.user_turn_expanded` action, one `prompt.sent`, and one `request.done`.
- `reason=new_user_turn`, `verification=full_prompt_in_new_user_turn`, complete expected/observed lengths and equal SHA-256 values. Extension delivery, a cleared editor and an implicit acceptance do not count as this proof.
- Authoritative remote completion at **00:52:16.645 UTC**; local verified acceptance at **00:52:18.268 UTC**, followed by harness finish at 00:52:18.275 UTC.

The authoritative answer was:

```json
{"begin_marker":"BRIDGE-LONG20K-BEGIN-741","end_marker":"BRIDGE-LONG20K-END-953","product":1591,"last_reference":"0140"}
```

See the [full per-turn evidence](runs/20261015-long-prompt/evidence/direct-long20k.json) and [manifest measurements and selection checks](runs/20261015-long-prompt/manifest.json).

## Direct-turn record

The following are distinct request identities. The 16k and 19k rows were retained as sent diagnostic failures; neither was relabeled not sent or replayed.

| Turn | Characters | Request ID | Client/tab | Conversation |
| --- | ---: | --- | --- | --- |
| [short preparation failure](runs/20261015-long-prompt/evidence/direct-short.json) | 655 | `mathagent_3c4a5bdd4b3d5c7c919b5e257b347882` | `1707788754` | New conversation not yet established |
| [short completed](runs/20261015-long-prompt/evidence/direct-short-e1.json) | 655 | `mathagent_37bfde9bb4fa538885a9c4a5188e160c` | `1707788754` | `6ad01f7f-aef4-83e9-8eb5-00f663f4f3a6` |
| [16k diagnostic](runs/20261015-long-prompt/evidence/direct-long-16000.json) | 16,198 | `mathagent_7434f370a49e54bcb53ee94e804e7ddc` | `1707788754` | `6ad01f7f-aef4-83e9-8eb5-00f663f4f3a6` |
| [19k diagnostic](runs/20261015-long-prompt/evidence/direct-long19k.json) | 19,660 | `mathagent_df5fe815b44d57c9a26de1f0789a2e6c` | `1707788757` | `6ad0227f-da38-83ea-b4f2-8be9ae3faf36` (read-only diagnostic identity) |
| [20k completed](runs/20261015-long-prompt/evidence/direct-long20k.json) | 20,236 | `mathagent_a91d1285a2885750b9f3288af583d3ae` | `1707788760` | `6ad023ba-7000-83ea-aba3-e98fcd4bdc9c` |

All times below are UTC on 2026-10-15. Dispatch is the measured start of the upstream POST. Terminal time is the authoritative stored turn's `completedAt`, including interruptions; it is not a success flag.

| Turn | Dispatch | Remote terminal | Outcome | Exact model/effort checks |
| --- | --- | --- | --- | --- |
| short preparation failure | 00:29:52.646 | 00:29:56.206 | Failed with positive pre-Send cancellation proof; [explicit not-sent acknowledgement](runs/20261015-long-prompt/short_not_sent_acknowledgement.json) | Pre GPT-6/xhigh; post not verified |
| short completed | 00:34:04.344 | 00:34:13.470 | Completed, full 655-character submitted hash | Pre/post GPT-6/xhigh |
| 16k diagnostic | 00:34:44.828 | 00:44:13.704 | Interrupted after confirmed actual submission; no accepted terminal answer | Pre GPT-6/xhigh; post not verified by terminal path |
| 19k diagnostic | 00:46:52.202 | 00:49:21.284 | Interrupted after confirmed actual submission; no accepted terminal answer | Pre GPT-6/xhigh; post not verified by terminal path |
| 20k completed | 00:52:07.086 | 00:52:16.645 | Completed, full 20,236-character submitted hash and exact JSON fields | Pre/post GPT-6/xhigh |

The 16k literal submitted DOM hash was `d75b4843b4b48a1370c5f834af68576aa878f85c5e4280074a8d02e5d0d88ca1`; the 19k hash was `04eb0eec0f26c9bc0e777436b33a9a83f785c05536533893a9b0203fbdf35da4`. Both matched their requested payloads. Visible replies and read-only recovery copies are forensic evidence, not fabricated authoritative completion records.

## Defects and focused changes

1. **The intended MAIN-world setter could not communicate.** The content script used `chatgpt-bridge-composer-*` while the registered MAIN helper used `chatgpt-browser-bridge-composer-*`. Correcting the channel exposed the real editor behavior instead of always timing out into paste.
2. **Multiline text needed the observed editing representation.** A real no-Send probe showed `<span data-prompt-literal-paste="">` with `<br>` nodes inside a paragraph. Writing raw newlines into paragraph `textContent` could produce spaces. Native escaped `insertHTML` now uses that observed structure; logical p/BR reading preserves line breaks, and complete text is verified before Send. Diagnostics record lengths, newline counts and first mismatch codepoints without logging payload text.
3. **Long submitted messages collapse at 10,240 visible characters.** The bridge expands only a new, non-baseline user turn whose literal text is an exact prefix of its fully prepared expected prompt, using that bubble's unique Show more control. It then checks the complete literal payload, excluding Show more/less UI text, and records SHA-256. Expansion never repeats Send.
4. **A stale observation target could leave confirmation pending.** The bounded acknowledgement waiter now re-reads current DOM as well as observing mutations, including a final inspection at timeout. The successful 20k run used this path. Delayed shared observations can also adopt only a complete matching new user turn from the original in-memory boundary.
5. **Pre-Send failure and post-Send uncertainty need different outcomes.** Exact source-proven preparation cancellation becomes an authoritative failed turn with `COMPOSER_TEXT_VERIFY_FAILED`, `provenNotExecuted=true`, and explicit cancellation evidence. After invoking Send, missing confirmation stays uncertain even if text remains. Reconciliation cannot automatically replay `prompt.submit` or `prompt.steer`.

The old [unsuccessful composer candidate](upstream_composer.patch) and [its status record](composer_fix_status.json) remain preserved separately. Its internal Show-control discrepancy was not retrospectively explained as opacity or a rendering race. The corrected patches are [composer/MAIN](upstream_long_prompt_v2.patch), [delivery state](upstream_delivery_state.patch), and [observation recovery](upstream_observation_recovery.patch).

**Recovery limitation:** pending expected text and new-turn baseline are content-memory projection fields, not persisted by the background lease/effect handshake. The observation fixture proves recovery given that projection; it does not prove persistence across document reload. The 16k/19k sent diagnostic requests were interrupted and preserved before deployment/reload, rather than replayed or adopted from an unrelated reply.

## Saved tree recovery and prompt efficiency

The four historical 13,065-character Parent attempts remain intact. Their allocation metadata can differ, so each complete payload was compared with its own immutable pre-work snapshot, not assumed identical. The explicit [historical audit](runs/20261015-long-prompt/historical_e3_verified_20261015T005023993578Z.json) fetched all four remote terminal records/events, verified source-level pre-Send proof, and compared the reopened Parent's two complete user-message hashes with the two completed local inputs.

The [apply result](runs/20261015-long-prompt/historical_e3_verified_20261015T005023993578Z.result.json) changed **only e3** to `FAILED_NOT_SENT`, preserved prompt/error/null response/request identity, advanced the exact retry key 3→4, and ran standard scheduler recovery with a transport that cannot dispatch. It released one error, reported zero pending turns and sent zero prompts. A database backup and immutable audit are retained. Generic interrupted requests, including the later sent 16k/19k diagnostics, are refused by this historical-only script.

The same fixed Parent and two Leaf conversations were [explicitly rebound](runs/20261015-long-prompt/tree_rebinding.json) to reopened disposable tabs: Parent 8745, Leaf 1 8748, Leaf 2 8751 (full Chrome IDs have prefix `170778`). Conversation IDs remained unchanged. The two already saved second-round Leaf reports were reused, with no additional leaf inference.

For the saved odd-sum second-round case, [offline prompt comparison](parent_prompt_comparison.json) reduced input from **13,065 to 10,988 characters (15.897%)**. The entire current structured report and its **3,491-character evidence** remain equal, with matching proof hashes and one current-report occurrence. Prior reports become durable references/summaries in the persistent chat; replacement sessions restore required history. Schema constraints and Python validation remain. This is an efficiency change, separate from the direct 20k transport pass.

The continuation reached **four complete, schema-valid report/Parent pairs**, two rounds for each child. The [read-only final audit](runs/20261015-long-prompt/tree_final_audit.json) confirms all four report hashes and both original Parent response rows are unchanged, each new response has exact child/round links, and each report, next prompt and Parent commit precedes the next leaf dispatch. The entire set of leaf turn IDs is unchanged. Both round-3 prompts were saved, and neither was dispatched.

| Child and round | Parent request | Input characters | Dispatch / authoritative completed UTC | Evidence |
| --- | --- | ---: | --- | --- |
| `n-e615a92f81c6-r000001` | `mathagent_a6fb321e31cf5211a3cc024c7d8a7776` | 8,261 | Referenced baseline | [Original completed Parent](runs/20261015-long-prompt/evidence/parent:n-e615a92f81c6-r000001:e0:a0.json) |
| `n-f9b4c78a7858-r000001` | `mathagent_ebcac79eee9057a6af8e4950c623fd22` | 8,281 | Referenced baseline | [Original completed Parent](runs/20261015-long-prompt/evidence/parent:n-f9b4c78a7858-r000001:e0:a0.json) |
| `n-e615a92f81c6-r000002` | `mathagent_3c7206a1075a570a9002290f262ea237` | 10,988 | 00:52:44.544 / 00:53:25.755 | [New completed Parent](runs/20261015-long-prompt/evidence/parent:n-e615a92f81c6-r000002:e4:a0.json) |
| `n-f9b4c78a7858-r000002` | `mathagent_ace904de6343588d9cef557b2b31df76` | 18,008 | 00:53:29.366 / 00:54:09.529 | [New completed Parent](runs/20261015-long-prompt/evidence/parent:n-f9b4c78a7858-r000002:e0:a0.json) |

Both new Parent turns used the same original persistent conversation `6acf41ec-72f8-83ea-a670-bfd46819ef79`, client `extension:tab:1707788745`, and exact GPT-6/xhigh verification before and after. Each recorded one Send, one own-message expansion and full requested/observed hash equality: `81986909dbf57c63aba1e4d2fb3bd368426ce67b56d42f37e665befa38414ef6` for 10,988 characters and `e4cd640b5d7d0b60b869f05128ef0d3e410eb7e3e0b6c4aa8df01344333275e1` for 18,008. Local verified acceptance was 00:53:27.513 and 00:54:11.670 UTC respectively.

The two new next prompts contain **2,655 and 3,590 characters**. Their exact schema links and hashes are in the final audit. Both children remain paused; no split, reweighting or third-round leaf inference was used to obtain this result. The disposable baseline had manual review disabled, and its saved review/capacity controls and approval hashes remained unchanged; this is not a new human-approval interaction.

## Optional Pro and math/code checks

The [00:56 UTC picker observation](runs/20261015-long-prompt/pro_availability.json) exposes checked GPT-6 and unchecked GPT-5.6 Sol, with Extra High at slider index 3 of 0–4. A visible locked access control does not establish an exact GPT-6 Pro identity. No exact GPT-6 Pro option was observed, no fallback was selected and **zero Pro inference requests** were sent. The production Pro default remains unchanged; its live pass is **BLOCKED**.

The first [math/code turn](runs/20261015-long-prompt/evidence/direct-math-code.json), request `mathagent_96cfdd250d03521fbfaa2f121f862b75`, authoritatively completed at **00:54:35.814 UTC**. Its answer retained exact TeX `\sqrt{2}+\frac{1}{2}+x_i^2` and both markers, but concatenated two rendered CodeMirror lines into `value = "sqrt(2)"print(value)`. This is **LIVE_FAIL for faithful fenced-code extraction**, despite successful submission and terminal completion. That original terminal is immutable.

Two read-only snapshots of that same existing reply remain separate: [00:58:17 snapshot](runs/20261015-long-prompt/math_code_readonly_recovery.json) still failed before the extension reload succeeded; [00:59:10 snapshot](runs/20261015-long-prompt/math_code_readonly_recovery_final.json) passed exact formula and two-line code checks after the correction was actually loaded. Their request identity is empty and their kind explicitly states no new inference. These snapshots demonstrate faithful extraction of the existing response; neither replaces the original terminal nor counts as a fresh successful inference.

The distinct [final math/code turn](runs/20261015-long-prompt/evidence/direct-math-code-final.json) is **LIVE_PASS**. Request `mathagent_5c10db4e14845c5ebe972b6a5dec88a3` used the existing probe conversation `6ad023ba-7000-83ea-aba3-e98fcd4bdc9c`, client `extension:tab:1707788760`. Exact GPT-6/xhigh checks passed before and after. Its 293-character payload's requested and submitted SHA-256 both equal `48746800239950c6b5f7b7f41273d57aa1de44bdf245562aafe9dcb2c71883ab`; full user-turn proof names `efd905a9-330f-4242-8ec5-2dcc2658a3ae::user`. Dispatch was **00:59:18.170 UTC**, authoritative completion **00:59:29.928 UTC**, locally verified acceptance **00:59:31.570 UTC**, and harness finish **00:59:31.584 UTC**.

The final authoritative answer retains both distinct markers `MATH-CODE-BEGIN-428` / `MATH-CODE-END-795`, exact rendered TeX `\sqrt{2}+\frac{1}{2}+x_i^2`, and a Python fence with exactly these separate lines:

```python
value = "sqrt(2)"
print(value)
```

The incremental [code-line patch](upstream_code_lines.patch) preserves observed CodeMirror `.cm-line` boundaries, indentation and blank lines without changing the retained math patch or original DOM. [Focused offline evidence](code_lines_unit_validation.json) remains separate from this live terminal pass.

## Reproducibility, tests and final state

The pinned upstream revision is `0ffdae90239988f253058c05253226152acd55d2` (bridge 6.4.1, extension 2.4.8). The four prior accepted picker/conversation/release/math patches were verified unchanged. Four incremental sets—long-prompt v2, delivery state, observation recovery and code lines—bring the accepted total to **eight**. The stable [bridge setup recipe](../../bridge/README.md) and [installer](../../scripts/setup_bridge.py) preserve reviewed patches without vendoring the upstream repository.

The [final installation verification](setup_verification_final.json) records all eight patches applied to a clean pinned checkout, exact final hashes for **17 unique reviewed files**, an idempotent second run, unchanged first four patch artifacts and a verified incremental math/code overlay chain. It checked syntax in 605 upstream files and the 340-file runtime package. The shipped code-line fixture passed. This setup validation started no browser or server and collected no credentials. The failed historical composer candidate is excluded.

Focused Python validation: **36 passed in 3.91 seconds** as reported by the implementation run. Offline upstream groups are recorded separately: **14 selector/request-machine checks**, **34 interaction/reconciliation checks**, **9 observation checks** and **5 DOM/parser checks**, all with zero failures. These are not added to a live inference count. The [composer/delivery fixtures](long_prompt_v2_unit_validation.json), [observation-only fixtures](observation_recovery_unit_validation.json) and [code-line fixtures](code_lines_unit_validation.json) cover multiline hashes, one Send, exact cancellation, refusal of uncertain replay, strict delayed anchors and faithful literal code. Prior math checks preserve radicals, fractions, powers, indices and literal inline/fenced code; the six earlier read-only DOM copies retained all 57 complete original annotations without altering terminal records.

The [clean source archive](../../dist/math-agent-long-prompt-fix.zip) contains **45 files**, all eight accepted patch sets, the stable code-line fixture, and a standalone [review summary](../../FIX_SUMMARY.md). Its SHA-256 is `5929281229be2f9463cb60d1347e638204694954ca6f4f2249b84a19044ff9f0`. The [package inspection](package_validation.json) verifies archive integrity, exact current source bytes, patch checksums, and summary links; credentials, databases, environments, caches, legacy copies and detailed live evidence are excluded. Production models, manual-review gates, optional communications, weights and maximum-only leaf capacity remain unchanged.

The optional Pro smoke can resume when exact GPT-6 Pro is selectable and verifiable in this same profile. No required long-input or four-pair test remains pending.

The [01:00:48 UTC cleanup record](runs/20261015-long-prompt/final_cleanup_long_prompt.json) confirms all experimental drivers exited and the bridge has **zero active requests, zero pending requests and zero pending commands**. The loopback bridge remains running as PID 67555 on **127.0.0.1:8080**. The existing Chrome process is still PID 8492, started October 8; it was not restarted and the profile was not changed. The original tab is present, unnavigated and unread.

Four result tabs remain: 1707788760 (direct long/math), 1707788745 (Parent), 1707788748 and 1707788751 (Leaves). Only disposable diagnostic tabs 1707788754, 1707788757 and 1707788742 were closed. All **22 baseline evidence-file hashes**, including the earlier RESULTS.md, remain unchanged. The [final live screenshot](runs/20261015-long-prompt/live_math_code.png) records the resulting math/code UI. Cleanup does not erase either known-sent interrupted diagnostic request.

The [final read-only recheck](runs/20261015-long-prompt/final_cleanup_recheck.json) reconnects the three retained tree tabs with the final parser, verifies exact GPT-6/xhigh selections again, and confirms zero active/pending requests or commands. The original tab and final source archive remain unchanged.
