# Bounded Phase 3 live research experiment

Overall verdict: **LIVE_FAIL** for the requested multi-round continuation. Genuine Pro remains **BLOCKED**. The run stopped after four real requests: one completed Parent bootstrap, two completed Leaf round-one reports, and one failed Parent assessment request. **0 of 6 requested Leaf Report → Parent Response pairs completed.** No second-round prompt was committed and no Leaf researched a second round.

Every experimental Leaf was explicitly labeled **`TEST_ONLY_EXTRA_HIGH_LEAF_OVERRIDE`** and actually selected **GPT-6 / Extra High** (`model-gpt-6`, `xhigh`). These are real ChatGPT web results in the existing Chrome profile, with **zero genuine Pro inference calls**. This run cannot establish that production Pro leaves work; exact-model availability is documented in [PRO_MODEL_DISCOVERY.md](PRO_MODEL_DISCOVERY.md).

## Scope and actual request record

The disposable problem investigates the optimal endpoint-zero discrete path Poincare inequality, equality cases, and near-extremizer stability. Parent proposed two complementary tasks: a spectral eigenvalue/equality investigation with relative weight 0.55, and an elementary finite-sum/ground-state-transform investigation with relative weight 0.45. Maximum capacity was four; Python created two useful leaves and left two slots unused. The topology was frozen for this bounded continuity exercise. Recursive splits and dynamic transitions were validated separately offline in [TREE_BEHAVIOR.md](TREE_BEHAVIOR.md).

The global [request ledger](request_ledger.json) records **4 unique requests out of the hard cap of 16**. All four crossed Send exactly once with full visible input hash/length confirmation. No request was sent after the halt. All timestamps below are UTC; `completedAt` for the final row is the bridge's failed terminal time, not a successful model completion.

| Operation | Actual request ID | Input characters | Actual Send confirmation | Upstream terminal time | Terminal status | Evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| Parent bootstrap | `mathagent_6b11c7b8d84959538a9d96da0b25d505` | 3,869 | 2026-10-15T06:33:09.209Z | 2026-10-15T06:34:21.106Z | **completed** | [Raw evidence](runs/live/evidence/bootstrap:root:e0:a0.json) |
| Leaf n-4360dde303ec round 1 | `mathagent_9c78d914743e56968af114c8c6944968` | 5,272 | 2026-10-15T06:42:18.216Z | 2026-10-15T06:43:41.022Z | **completed** | [Raw evidence](runs/live/evidence/leaf:n-4360dde303ec-r000001:e0:a0.json) |
| Leaf n-952ae628fa68 round 1 | `mathagent_007d00f57c7259f394d556a0b4cfcb63` | 5,625 | 2026-10-15T06:42:19.762Z | 2026-10-15T06:43:49.655Z | **completed** | [Raw evidence](runs/live/evidence/leaf:n-952ae628fa68-r000001:e0:a0.json) |
| Parent assessment for spectral Leaf round 1 | `mathagent_8dead57559845377aa96cac3e5f68d83` | 16,701 | 2026-10-15T06:43:50.556Z | 2026-10-15T06:44:16.437Z | **failed** | [Raw evidence](runs/live/evidence/parent:n-4360dde303ec-r000001:e0:a0.json) |

Each completed reply has exact-model/effort checks before dispatch and after terminal observation, request-matched authoritative output, and raw bytes identical to the durable local response. The failed Parent attempt has pre-dispatch model verification and full Send proof, but has no accepted terminal answer or post-answer model proof. Its visible DOM reply remains a separate candidate below.

## Persistent independent conversation identity

The completed bootstrap and Leaf replies establish these three distinct bindings:

| Node | Durable session | Extension client | Persistent ChatGPT conversation |
| --- | --- | --- | --- |
| `root` | `S-69635a7172cd5208bd84c81f96463809` | `extension:tab:1707788777` | `6ad073a4-b6b0-83ea-8d27-eb898d8fc2c1` |
| `n-4360dde303ec` | `S-d75123477e0959698b89b85a1d195977` | `extension:tab:1707788780` | `6ad075c9-dc9c-83e9-969e-6b6ab3986682` |
| `n-952ae628fa68` | `S-2d3671c801d4594f811798a03cc852a0` | `extension:tab:1707788783` | `6ad075cb-4900-83ea-8233-273180550313` |

The failed Parent assessment reused the bootstrap Parent conversation `6ad073a4-b6b0-83ea-8d27-eb898d8fc2c1`. All request metadata required `model-gpt-6` and `xhigh`; empty upstream model/effort selectors preserved the exactly verified picker choice. The [independent saved-evidence audit](live_protocol_audit.json) checks source client, terminal conversation, input content, full submitted text, model observations and local/raw terminal equality. It made no browser, bridge or inference calls.

A persistent binding is not sufficient evidence of genuine model recall. The two diagnostic context-only follow-ups were **NOT_RUN**, with **0 context-probe calls**, because the first Parent assessment failed before any multi-round continuation. The prepared diagnostic helper was never executed. Prior baseline context evidence remains historical evidence and is not relabeled as a Phase 3 success.

## What completed, and what remains mandatory

Both completed Leaf responses are schema-valid `LeafRoundReport` objects with full mathematical evidence:

- The spectral Leaf derives the complete finite-difference spectrum, sharp constant, equality family, and the small-size exception without introducing a nonexistent second eigenvalue.
- The elementary Leaf derives a ground-state-transform identity, checks endpoint contributions, computes sharpness directly from finite sums, and audits the first two sizes.

These are model-proposed mathematical results. A `SOLVED` value describes the model's round status; it does not establish independent verification or acceptance of the entire stability program.

| Durable round | Leaf's reported status | Durable protocol stage | Parent response committed | Next round |
| --- | --- | --- | --- | --- |
| `n-4360dde303ec-r000001` | SOLVED | AWAITING_PARENT_RESPONSE | False | None |
| `n-952ae628fa68-r000001` | SOLVED | AWAITING_PARENT_RESPONSE | False | None |

Both reports remain stored with their exact node/round IDs and immutable raw replies. The spectral Leaf has a visible recoverable Parent transport error. The elementary Leaf's mandatory Parent assessment was never dispatched after the halt. Neither missing Parent response is counted as completed or silently ignored. The authoritative tree has **2 reports, 0 Parent responses, 0 linked next prompts and 0 completed pairs**. The saved [tree summary](runs/live/tree_summary.json), [manifest](runs/live/manifest.json) and [protocol audit](live_protocol_audit.json) retain this incomplete state.

The [Research Report](runs/live/project/RESEARCH_REPORT.md) mirrors Root and both Leaf headings, but has **0 published finding sections**. Optional publication stayed behind the unsettled mandatory Parent checkpoint. The full mathematical evidence remains in round history; it was not prematurely presented as accepted or independently verified report prose.

## Failure, observed candidate, and safe stopping

The Parent assessment request `mathagent_8dead57559845377aa96cac3e5f68d83` was verifiably submitted with **16,701 characters** and SHA-256 `bcc21af483ea8258fd188239ab8c7b5dc600182a41203dfbc3c846b066b60b48`. It subsequently reached the canonical bridge failure:

```
CANONICAL_RECOVERY_UNCERTAIN
The submitted user turn disappeared after content reload;
repeating prompt.submit would be ambiguous and is forbidden.
```

This is what the bridge reported. A later read-only UI observation found that the exact rendered user input was still present, with the same hash and confirmed user-turn key `c27f4451-1b2b-4d48-bbeb-3a35ee7daae0`. It also found an assistant JSON candidate with matching child/round IDs and a schema-valid **4,946-character** next task. The candidate's hash is `00a8b4a7e53d3530d6e1d81f807ca777337732e59597cf79a05102285ab63cc3`.

The candidate is classified **READ_ONLY_DOM_CANDIDATE_NOT_COMMITTED**. The bridge terminal remains `failed`, local status remains `ERROR`, `raw_response` remains null, and committed Parent pairs remain **0**. It was not inserted as an authoritative response, used to approve a gate, dispatched to a Leaf, or counted as a live pass. See the [captured candidate](parent_recovery_candidate.json), [validation](parent_candidate_validation.json), and [screen](parent_recovery_candidate.png).

Source investigation identified a legacy role lookup in projected boundary recovery that misses the current user/assistant DOM wrappers. The additional three-line `resume_roles.patch` reuses the existing current-DOM role helper. The targeted offline fixture reproduces the original failure and verifies correct exact-boundary matching after the fix, unchanged legacy/missing-boundary behavior, and zero Send calls. All nine patches apply idempotently to a fresh pinned checkout, and 23 focused upstream tests pass. See [repair validation](resume_roles_validation.json). The eight earlier patch files and their historical live evidence remain unchanged. The installed extension and active checkout still have only those eight patches; the new repair is **OFFLINE_PASS, not deployed, live retest NOT_RUN**. It does not change the failed request retrospectively.

The harness stopped on this uncertainty, retained the failed request identity, and issued **no resend**. Positive input/DOM evidence does not authorize silently repeating a possibly completed inference. Further automatic continuation and context probes remain blocked pending explicit reconciliation.

## Actual overlap, distinct from request timing

The two Leaf requests overlapped for **85.094873459 seconds** between dispatch and authoritative terminal receipt. This is a request-window measurement, not proof of simultaneous inference.

Separately, request-matched, fresh generation observations establish **38.519000292 seconds of observed two-Leaf generation overlap**. The audit constructs intervals only between distinct active observations no more than two seconds apart, bounded by the specific dispatch and upstream completion timestamps. Cached single observations and larger gaps do not count. Activity between samples is inferred at that resolution; brief unseen transitions remain possible. The exact intervals and limitations are retained in [live_protocol_audit.json](live_protocol_audit.json). No three-node generation-overlap claim is made for this run.

## Idle restart and recovery boundary

The deliberate restart exercise occurred **after bootstrap completion and before Leaf dispatch**, while bridge work and local unresolved turns were zero. The before snapshot was recorded at `2026-10-15T06:41:53.349928+00:00`; the after snapshot at `2026-10-15T06:41:57.874795+00:00`. Durable hashes for nodes, sessions, turns, rounds, Parent responses and approvals matched exactly: **LIVE_PASS for this idle restart check**. See [before restart](runs/live/idle_before_restart.json) and [after restart](runs/live/idle_after_restart.json). This does not prove safe recovery of the later ambiguous Parent attempt, which was deliberately left unreplayed.

Final current bridge health, pending human-review state, browser preservation and source-package details are documented in [SUMMARY.md](SUMMARY.md). No historical failures or previous successful experiment reports were overwritten.
