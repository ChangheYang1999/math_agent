# Math Research Tree — consolidated debugging release

The existing Python scheduler, durable tree and mandatory **Leaf report → Parent assessment → saved next prompt** cycle are preserved. Production Leaves require GPT-6 Pro; internal nodes require independent persistent GPT-6 / Extra High conversations.

## Implemented fixes

- **Repeated-looking approvals:** the user's original approval succeeded. Twelve distinct prompt/report approvals advanced six scripted demonstration rounds; successive items looked alike. The dashboard now shows exact artifact identity and queue position, authoritative receipts, approved/execution history, disabled submitting controls, visible HTTP errors and stale-poll suppression. All original approvals remain unchanged. Approval and dispatch are separate states.
- **Actual Pro selection:** the adapter recognizes either a dedicated GPT-6 Pro model or the current exact GPT-6 family plus Pro intelligence. Parent selection still requires Extra High. Positive checks before and after each request reject other families/tiers. Production defaults remain unchanged.
- **Explicit recovery:** source-bound validators and idempotent local commits recover existing completed answers using exact request, conversation, user/final identity, terminal status and full content evidence. Original failed terminals and source rows remain intact. Recovery uses ordinary report approval gates and Parent transactions, sends no prompt, and releases only the exact committed receipt.
- **Focused bridge repairs:** final assistant extraction avoids the reasoning recap; model discovery activates only its existing target tab and cancels stale waits; two existing text readers recognize ChatGPT's new rich user-message root while retaining strict full-content confirmation. Future response templates request fenced JSON to preserve mathematical strings. Existing stored prompts and approvals are unchanged.

## Actual validation

**LIVE_PASS — bounded production-role research:** two genuine GPT-6 Pro Leaves each completed three rounds, with all **six exact Leaf Report → Extra High Parent Response pairs** saved. The final Parent terminal completed on 2026-10-15 at 10:10:31 UTC. All report/Parent IDs and mandatory event order passed. Both fourth-round prompts are saved and undispatched; both Leaves are paused. The ledger contains **14/16 reservations**, including one proven pre-delivery busy rejection: 13 distinct submitted inference requests. No uncertain submitted request was repeated. Several original capture failures required separately audited recovery; this was not a failure-free run.

Normal full-text submission succeeded for a 28,618-character Parent prompt. After the rich-reader repair, another actual 23,768-character rich prompt automatically expanded, matched its entire hash, submitted once and completed normally. The original browser/profile and unrelated original tab remain preserved; final model checks passed and Bridge work is idle. No API inference substituted for browser results.

The final publication audit caught an experiment-only deferred-section ordering defect. The harness now flushes all sections in original insertion order after the six-pair boundary. A backed-up, append-only repair republished the exact latest saved Root and spectral findings, preserving all original research rows and section history. It used zero inference.

**OFFLINE_PASS:** 47 focused production regressions passed in 6.684 seconds; Ruff passed. The publication harness received one additional focused temporary-database regression. Bridge verification includes 41 focused upstream checks and actual captured-DOM fixtures; these are distinct from live results.

## Bridge patch status

Pinned upstream: `0ffdae90239988f253058c05253226152acd55d2` (Bridge 6.4.1, extension 2.4.8). The original eight accepted patch artifacts remain byte-identical. All twelve accepted patches replay strictly and are included.

| Patch sets | Evidence-backed status |
| --- | --- |
| Original eight | Historical live-verified artifacts preserved |
| Ninth, resume_roles | Installed and offline/current-DOM checks passed; live request.resume handler execution NOT_RUN |
| Tenth, final_answer | Actual final extraction and fenced-content fidelity passed; legacy plain-Markdown underscore/emphasis fidelity remains KNOWN_FAIL |
| Eleventh, picker_activation | Actual exact model/effort reads passed after deployment |
| Twelfth, user_payload | Actual rich-root automatic full-content expansion, single Send and normal completion LIVE_PASS |

The latest supported extension maintenance reload returned HTTP 200 after all owned requests were terminal. No further manual Reload is required. An earlier maintenance timeout remains recorded separately.

## Remaining boundaries and human action

The separate real bridge-provider manual-review project at http://127.0.0.1:8767/ now has a **genuine HUMAN_APPROVED Prompt**, personally accepted by the user on October 15, 2026 at **8:21:26 a.m. PDT**. It is node `n-10712a75c7a1`, round 1/version 1, exact hash beginning `1b9e4c081c99`. Read-only SQLite and the refreshed real dashboard confirm **APPROVED / WAITING_FOR_DISPATCH**, zero pending reviews and no reopened popup. No repeat approval is needed. The project remains PAUSED with no scheduler worker, sessions or model turns, as promised. Its genuine Pro turn, Report gate and complete manual-review cycle remain NOT_RUN. No agent approved it. The earlier 8766 demonstration's twelve genuine user approvals remain preserved; its mathematical replies are explicitly simulated.

The historical Extra High-only halted experiment has one separately recovered Parent pair and an unchanged sibling obligation. It is not counted toward the six new genuine-Pro pairs. Unaided new recall and live recursive promotion remain NOT_RUN; recursive allocation, P0 priority, optional communication and role promotion retain their focused offline passes. Native simultaneous generation was observed in two owned tabs within the captured sampling window; no sustained or three-way generation claim is made. Model-proposed mathematical findings are not independently verified.

## Run and review

Use Python 3.11+ in an activated environment:

```sh
python -m pip install -e .
python scripts/setup_bridge.py
mathagent init my-research --file problem.md --transport bridge --review
mathagent dashboard my-research
```

Follow `bridge/README.md` for the pinned setup, existing Chrome profile, extension and exact per-node picker selection. Read `README.md` for workflow and recovery instructions. The source-only package excludes experimental databases, private raw evidence, credentials, browser data, caches, virtual environments and upstream dependencies. Detailed live evidence remains in the original workspace under `experiments/consolidated_debug/`.
