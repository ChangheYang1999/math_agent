# Dynamic Research Tree validation

Verdict: **OFFLINE_PASS**. All new structural, allocation, communication and model-transition checks used the explicitly scripted transport in fresh isolated projects. No browser request or Pro inference was performed by these tests. Genuine Pro → Extra High model switching remains **BLOCKED / NOT LIVE VERIFIED** until an exact selectable Pro model is available. The separate live experiment, if run, is documented in `LIVE_RUN.md` and does not upgrade this verdict.

## Demonstrated defect and focused change

Before the fix, `tick()` counted every unfinished child round as mandatory work. Every successful Parent response creates a saved next prompt, including prompts held for review or in paused leaves. Consequently a meaningful internal message stayed `PENDING` after 100 ticks although the earlier report already had its Parent response. The original failing synthetic state is preserved in [tree_message_before_fix.json](tree_message_before_fix.json).

The small change in `scheduler.py` treats `SOLVING`, `REPORT_APPROVAL` and `AWAITING_PARENT_RESPONSE`, plus newly launched Leaf tasks, as busy. A saved undispatched prompt is now an eligible boundary for optional coordination. Unapproved reports remain blocking and are not supplied as approved results. Parent response/next-prompt persistence still precedes optional work; no research loop, model contract or tree schema was rewritten.

## Recursive structure and role transition

The synthetic Fibonacci gcd task creates useful algebra/reduction branch A and boundary-case branch B. After A completes one approved simulated report/Parent pair, A is split into an addition-identity task A1 and a Euclidean-reduction task A2:

```
Root (root)
├── Internal A (n-3763f593a5b0)
│   ├── A1 (n-3fa7ea55bfe7)
│   └── A2 (n-71f9b5bce15a)
└── Leaf B (n-ca7fd7a5632d)
```

A's old scripted Pro session `S-19159549dbfc5326923b268530de07d4` is retained with `active=0`. Its independent coordinator session is `S-ac427ade7def5b91b42be9438379b62a`, model `GPT-6 Extra High`. The original Leaf report SHA-256 remains `f76740365fcd776486f44fe1c22278fe450f053709c0d2046200e83d622b9e97` after promotion. Full report history, the linked Parent response and the superseded saved next task are retained. Children receive concrete English prompts and durable prompt gates. This proves the local role/session protocol only; it is not genuine Pro model selection evidence.

## Weights, capacity and boundary behavior

Root absolute weight stays 1. Each active sibling allocation sums to 1; absolute child weight equals parent absolute weight times its relative share. Capacity 8 creates only three useful active leaves after the recursive split; five slots remain unused. The program creates no placeholder tasks to fill them.

| Snapshot | Root active leaves/capacity | A/B relative shares | A/B leaf capacity | B status |
| --- | --- | --- | --- | --- |
| initial | 2/8 | 0.75 / 0.25 | 6 / 2 | ACTIVE |
| recursive | 3/8 | 0.75 / 0.25 | 6 / 2 | ACTIVE |
| reweighted_down | 3/8 | 0.5 / 0.5 | 4 / 4 | ACTIVE |
| zero_paused | 2/8 | 1 / 0 | 8 / 0 | PAUSED |
| resumed | 3/8 | 0.75 / 0.25 | 6 / 2 | ACTIVE |

The zero-weight B branch pauses before dispatch. Its original prompt remains gated; resuming and restoring the 0.75/0.25 allocation returns capacity 2 without running it. The existing focused contraction test additionally holds two Leaf turns in progress, reduces one branch to zero allocated slots, and checks that its actual report and Parent response finish before it becomes paused; its concrete next prompt remains saved and undispatched.

## Event-driven communication and priority

A sends exactly one meaningful message to Root about boundary-index conventions, with a reason and an approved report reference. It is delivered at the saved-prompt boundary after the fix. The payload and reference are in [offline_tree_evidence.json](offline_tree_evidence.json). Other coordination calls arise only from the explicit allocation changes. Five additional unchanged ticks produce no new internal conversation work: no periodic internal meeting or automatic report forwarding was introduced.

The retained tests also cover P0 Parent feedback while another Leaf is still solving, persistence of the next task before optional publication, an optional reweight failure remaining visible without setting unrelated nodes to `ERROR`, and no duplicate uncertain-send recovery. Optional failures are not a universal scheduler lock.

## Research Report

The report builder derives the hierarchy from parent relations. Nodes update only their own sections; changing A's section preserves Root's text and all descendant headings. A cross-owner update is refused. A model's own proposed proof cannot become `VERIFIED` without an independent verification reference. Ordinary unsuccessful rounds remain in node history rather than automatically becoming formal report prose.

The actual isolated report outline was:

```
# Research Report
## 1 Investigate the Euclidean gcd identity for Fibonacci numbers. [ACTIVE]
### 1.1 Derive the addition and Euclidean reduction identities. [ACTIVE]
#### 1.1.1 Use the addition identity to justify Euclidean reduction. [ACTIVE]
#### 1.1.2 Derive the Fibonacci addition identity with explicit indices. [ACTIVE]
### 1.2 Check the zero-index and divisibility boundary cases. [ACTIVE]
```

## Evidence and validation

- [offline_tree_evidence.json](offline_tree_evidence.json): before/after allocation snapshots, exact session IDs, preserved report hash, approvals, rounds, events, meaningful message and report outline. All records are labeled `OFFLINE_SIMULATION`.
- [tree_validation.json](tree_validation.json): essential regression command and outcome, **22 passed in 3.73 seconds**, Ruff passed.
- New coverage is one integrated deterministic scenario in `tests/test_tree_dynamics.py`; existing focused tree protocol cases were reused.
- No existing research project/database, previous evidence, bridge patch, production role/default or user conversation was modified by this validation.
