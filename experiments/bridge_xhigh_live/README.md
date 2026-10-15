# Live Extra High browser experiment

The [long-prompt continuation report](RESULTS_LONG_PROMPT_FIX.md) records the
20,236-character live pass, all four completed saved tree pairs, faithful math/code
extraction, and the exact Pro availability blocker. See [FIX_SUMMARY.md](FIX_SUMMARY.md)
for the focused implementation and [bridge setup](../../bridge/README.md) for the
reproducible installation. The earlier [RESULTS.md](RESULTS.md) remains unchanged.

`run_experiment.py` drives the existing production `BridgeTransport` and, optionally,
the real Research Tree `Scheduler`. It has no mocked responses, paid inference API,
browser launch, or per-message GUI operator. It is a bounded experiment, not an
always-running research service.

Prerequisites are the **already running**, logged-in Chrome profile, an authorized
DrA1ex/chatgpt-bridge extension connected to the localhost bridge, and exact GPT-6
Thinking / Extra High selected in each test tab. Root browser setup and inspection
must establish these facts before releasing a command that sends messages.

The inspected upstream is commit `0ffdae90239988f253058c05253226152acd55d2`.
Its durable turn queue has distinct `sourceClientId` lanes; this supports the test
design but does not establish that live generation actually overlaps.

## Commands

Run from the repository root with its existing Python environment. Provide
`MATHAGENT_BRIDGE_API_TOKEN` in the process environment without printing it.
Only loopback `MATHAGENT_BRIDGE_BASE_URL` values are accepted.

The default exact model label is `GPT-6 Thinking`. If actual live discovery and GUI
inspection instead show the GPT-6 radio label `GPT-6`, pass
`--actual-model-label 'GPT-6'` on **every** command for a fresh run. This opt-in label
is saved in that run's manifest and disposable database; changing it on resume is
rejected. Production defaults are unchanged, and exact Extra High remains required.

```sh
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID init
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID prepare --group smoke
# Inspect the newly created smoke tab and select the exact model and effort.
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID verify --group smoke
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID smoke

.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID prepare --group parallel
# Inspect only the three new experiment tabs; verify their exact selections.
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID verify --group parallel
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID parallel
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID context
```

`init`, `prepare`, `verify`, and `status` send no prompts. `prepare` opens only
dedicated new tabs through the bridge; it never binds an unrelated existing tab.
`parallel` and `context` each use `asyncio.gather` with one adapter instance so
selection/discovery remains serialized while independent turn requests overlap.
The exact supplied proof prompts and markers are preserved.

Do not invoke later phases if a prerequisite fails. Repeating a command uses the
same local turn IDs and existing durable bridge records, avoiding duplicate sends.
An uncertain delivery stays uncertain until the original server turn is queried;
the driver does not generate a replacement request ID.

If three requests produce an explicit authoritative capacity failure, one bounded
two-request diagnostic is available. All three original requests must first have
known terminal states; uncertain delivery and ambiguous errors prohibit this probe.
It uses two fresh tabs because a failed old conversation may retain an unresolved
local turn. It never retries an uncertain message or claims a three-request pass:

```sh
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID prepare --group two
# Select and verify the exact model and effort in these two new tabs.
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID verify --group two
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID parallel-two
```

Repeated calls use the same two durable request IDs and do not add new probes.

Optional tree commands require passing smoke, three distinct replies, context,
in-flight overlap, and fresh browser observations of three simultaneous generations:

```sh
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID prepare --group tree
# Verify the exact selections in these three new disposable tree tabs.
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID verify --group tree
.venv/bin/python experiments/bridge_xhigh_live/run_experiment.py --run RUN_ID --tree-pairs 2 tree
```

Two pairs complete one leaf report/parent-response cycle for each of two leaves;
`--tree-pairs 4` also permits a second cycle per leaf when scheduling is balanced.
The local `ExperimentScheduler._session` override maps leaf requests to the parent
model **only inside this disposable driver**. Production Pro/Extra High policy and
settings remain unchanged. Model reasoning is never replaced with script output.
The three prepared nodes are frozen: optional tree changes and inter-node messages
remain saved as deferred proposals, and each leaf's limit is checked before dispatch.
Rerunning an already complete bounded tree does not send further messages.

## Evidence and interpretation

Each run is isolated under `runs/RUN_ID/`; existing `projects/` are untouched.
`manifest.json` is saved incrementally, and `results_rows.json` contains the requested
report-table fields. The root agent writes the final human-readable `RESULTS.md`
using actual execution evidence, including blockers when setup cannot finish.

`evidence/*.json` saves each experiment turn's authoritative server terminal record,
own prompt/answer, lifecycle events, and wall/monotonic dispatch and completion
measurements. Requested model identifiers are distinguished from picker snapshots
in `selection_checks`. Header values and credentials are never collected; token
fields and the environment token are additionally redacted before artifact writes.

Concurrent HTTP calls alone do not prove simultaneous generation. The observer
polls `/browser/clients` and retains only experimental tab IDs, own active request
IDs, and generation telemetry. It derives activity intervals only from consecutive
fresh observations of the same experiment request that explicitly report
`generation.state == "active"`, with at most two seconds between observation times.
Repeated cached timestamps do not create intervals. Intervals are clipped to actual
dispatch and the earlier of upstream completion or received terminal result.
Three-way generation evidence requires an intersection of all three request-specific
activity intervals. Sampling cannot rule out brief transitions between observations;
this limitation is saved with the measurements. Three-way in-flight overlap is computed separately
from actual dispatch POST to accepted authoritative terminal result. Resumed turns
from different processes do not receive a synthetic monotonic overlap estimate.

Markers, persistent IDs/URLs and simple task relevance are checked automatically.
The saved complete proofs still require human mathematical inspection; relevance
checks do not constitute independent proof verification. If tabs work but their
generation intervals serialize, report `MULTI_TAB_WORKS_BUT_NOT_CONCURRENT`.

The driver never closes any browser tabs, so all test conversations remain
available for inspection. Workloads stop at the requested pair count or failure.
It does not interrupt or cancel an uncertain upstream turn on exit; inspect that
same durable request before any manual recovery.

`write_report.py` renders saved manifests and own terminal evidence without live
calls. Its default is stdout, preserving `RESULTS.md` until explicitly requested:

```sh
.venv/bin/python experiments/bridge_xhigh_live/write_report.py
.venv/bin/python experiments/bridge_xhigh_live/write_report.py --output experiments/bridge_xhigh_live/RESULTS.md
```

The default includes both the initial failed run and `20261014-live-r2`; repeat
`--run RUN_ID` to choose other saved runs. Additional factual handoff notes can be
supplied with repeatable `--note` arguments. Unknown fields remain `NOT_VERIFIED`.

## Recorded live outcome and remaining limitation

See `RESULTS.md` for actual evidence. The smoke, three-conversation concurrency,
and context-retention tests passed. The Research Tree completed the required two
report/parent-response pairs and dispatched both next rounds in the correct order.
Both second-round leaf reports also completed. The extended four-pair target did
not finish: a 13,065-character parent prompt became a pasted-text attachment before
submission. All four preparation attempts were safely interrupted and preserved.
No inference is running or automatically scheduled.

The picker, conversation identity, release settlement, and math extraction patches
are retained. `upstream_composer.patch` is an unsuccessful **NOT APPLIED** candidate;
`composer_fix_status.json` distinguishes its passing synthetic fixtures from failed
live behavior. The installed composer was restored to exact upstream HEAD. The
composer fixture is retained for investigation against that candidate, and is not
a test of the active restored composer. Inspect saved results without rerunning
messages; further extended integration requires resolving this input issue first.
