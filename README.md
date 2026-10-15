# Math Research Tree

A local recursive research tree using persistent ChatGPT web conversations. Each leaf has its own
**GPT-6 Pro** conversation; the root and internal nodes each have a separate **GPT-6 Thinking / Extra High**
conversation. Python owns scheduling and SQLite state. Research reasoning stays in ChatGPT web;
no billed OpenAI inference API is used.

Every round follows **saved parent prompt → leaf report → parent assessment and saved next prompt**.
A leaf cannot continue on its own. Raw replies, exact prompts, reports, approval versions, and
conversation bindings survive restart. Model-proposed mathematical claims remain unverified.

## Install and offline demo

From this folder, with Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mathagent demo tree-demo --rounds 2
mathagent dashboard tree-demo --open
```

Use a fresh demo name if it already exists. The demo stops after two complete report/parent-response
pairs and leaves the next prompt saved. Opening its dashboard resumes fake research; use Pause to
inspect a fixed checkpoint. The Chinese dashboard listens only at [127.0.0.1:8765](http://127.0.0.1:8765).
Start one `run` or `dashboard` process per project.

## Real research through manual relay

```bash
mathagent init my-research --file problem.md --review
mathagent dashboard my-research --open
```

The default `manual` transport queues complete prompts. Create one ChatGPT conversation per node,
select its exact model/effort, bind its conversation URL, copy the prompt, and paste the actual full
reply after generation finishes. Conversations are reused. Manual relay always requires human
interaction, including when review is OFF. `--goal "English problem statement"` and `--file -` are
alternatives to a problem file.

## Browser bridge setup

The adapter targets [DrA1ex/chatgpt-bridge](https://github.com/DrA1ex/chatgpt-bridge), a third-party
Chrome extension and local server. Use the [pinned setup recipe](bridge/README.md),
which preserves the verified picker, conversation, release, math, long-input,
and explicit delivery/recovery fixes:

```bash
python3 scripts/setup_bridge.py
cd ~/.local/share/math-research-agent/chatgpt-bridge
HOST=127.0.0.1 AUTO_OPEN_TAB=false BRIDGE_STARTUP_EXTENSION_RELOAD=never \
node src/index.js --server --no-auto-open-tab --no-reload-extension
```

In Chrome, open `chrome://extensions`, enable Developer mode, Load unpacked, and select
`~/.local/share/math-research-agent/extension`. Open [the bridge setup page](http://127.0.0.1:8080/setup),
copy its masked **BRIDGE_TOKEN**, and open the extension's toolbar action in a new ChatGPT tab
to connect it. Reuse your existing logged-in Chrome profile and preserve original conversations.
Stop the foreground server with Ctrl+C after requests are terminal. See the recipe for updates,
extension reloads, alternate paths, and private data preservation.

HTTP clients use a **different API_TOKEN**, generated in `~/.bridge-data/.env`. In the shell where
you run Math Research Tree, set that value without putting it in project files:

```bash
export MATHAGENT_BRIDGE_API_TOKEN='your-bridge-API_TOKEN'
# Optional if the bridge uses another local port:
export MATHAGENT_BRIDGE_BASE_URL=http://127.0.0.1:8080
```

Return to this repository, activate `.venv`, then run:

```bash
mathagent diagnose my-research --transport bridge --json
mathagent dashboard my-research --transport bridge --open
```

Diagnostics read connection health, sessions, visible models and efforts without sending research.
The dashboard shows each node's recorded bridge client/tab, conversation, and selected identifiers.
New nodes get dedicated tabs. **Choose the required model/effort in each new tab, then use Recover**
if it is waiting at `MODEL_UNAVAILABLE`. Leaves require GPT-6 Pro; parents and the isolated boundary
translator require GPT-6 Thinking with Extra High. Identifiers are discovered from the actual UI;
configuration defaults do not prove that your account exposes these options.

The inspected extension uses fuzzy picker matching: requesting `xhigh` can also match `high`.
Consequently the adapter preserves an already exact selected model/effort and sends no picker-change
selectors. It checks the exact bound tab before dispatch and after completion. Initial tab/model
setup is manual; do not change the model or navigate that tab during a turn. A missing or changed
selection produces a visible error instead of a fallback.

The adapter uses the upstream [durable turn API](https://github.com/DrA1ex/chatgpt-bridge/blob/0ffdae90239988f253058c05253226152acd55d2/src/routes.js)
(`POST /turns`, `GET /turns/:id`, and its SSE events), preserving request IDs and accepting only the
stored terminal response. Interim previews never become reports. Restart reconciles the same turn;
an uncertain dispatch is never automatically sent again. `MODEL_UNVERIFIED` requires inspecting the
original chat and explicit manual-relay confirmation; restoring the picker alone cannot approve it.

**Recorded live baseline:** three independent Extra High conversations completed concurrent
proofs and retained their own context; two real leaf-report/parent-response pairs completed.
The extended tree run exposed a long-prompt composer failure, preserved in
[the experiment report](experiments/bridge_xhigh_live/RESULTS.md). Synthetic tests and HTTP
acceptance alone do not establish successful live submission. Live operation requires a compatible
connected extension, normal login, and exact model/effort access.

## Review: four separate actions

`manual_review_enabled` defaults to OFF. ON requires explicit local approval of both the exact
prompt before Pro dispatch and the exact report before its parent's next decision. The dashboard
automatically opens one review modal at a time and retains all pending items in the inbox.

- **Approve** accepts only the displayed hash/version.
- **Ask Parent** supports repeated questions about that artifact. It changes no approval, round,
  prompt, report, or research state. The entire discussion survives refresh/restart.
- **Request Revision** explicitly changes the workflow. A prompt gets a superseding version and
  another approval. A questioned report remains immutable and unaccepted; its parent creates a
  linked correction prompt that also requires approval.
- **Later** closes the modal and retains the pending review. Closing/Escape never approves.

Chinese questions cross an isolated translation boundary; research conversations receive English.
Chinese display replies retain accessible English originals. Explicit formulas and LaTeX spans are
checked for preservation. Discussion uses the relevant leaf's existing Extra High parent, and
queued mandatory parent decisions take priority over further discussion. Browser notifications
require permission and an open page; pending reviews surface when the dashboard reopens. Switching
review OFF records automatic release of pending gates; ON applies to gates not yet crossed.

## Capacity, persistence, and reports

`max_active_leaves` is an upper limit. The old `target_active_leaves` configuration key remains
accepted and is retained in saved settings. Weights allocate **leaf_capacity**, not tasks to invent.
With capacity 20, a subtree may use only 3 of its 12 allowed slots indefinitely. `unused_capacity`
is normal. Splits require genuine concrete tasks and must fit their weighted cap. Reductions pause
work at safe boundaries, after any running attempt's report and parent response are saved.
`max_concurrent_pro_turns` separately limits simultaneous Pro replies.

P0 finishes the mandatory protocol and review gates. P1 handles conditional tree changes and rare,
event-driven messages. Failed optional actions stay visible and require explicit recovery; they do
not block unrelated P0 work. Pending pause/complete/split actions block only conflicting dispatch.
P2 updates the English `RESEARCH_REPORT.md` on significant findings, with sections matching the tree.
Each node owns its section. Reweighting and paused directions preserve established results.

Research Tree databases upgrade in place from schema 1 to 2 without erasing history or bindings.
Older Brain/Branch/Probe `state.db` projects are preserved but are not converted to Research Trees.
Back up the entire project directory, including SQLite sidecars, after stopping its runtime.

## Commands, configuration, and packaging

```bash
mathagent --projects-root projects --config config.example.yaml init another-project --file problem.md
mathagent status another-project --json
mathagent diagnose another-project --transport bridge
mathagent recover another-project
mathagent run another-project
```

Configuration is saved at initialization; later runs use saved SQLite settings. The global `--config`
option configures new projects and project-root lookup. `--transport` overrides a run/dashboard/diagnose
process. Bridge token and base-URL environment overrides apply to existing projects too. See
[config.example.yaml](config.example.yaml) and [.env.example](.env.example).

Build a clean source ZIP (no research, environments, caches, tokens, or historical code):

```bash
python scripts/package_source.py /tmp/math-agent-source.zip
```

One local `.venv` is retained for running this workspace and is excluded from source distributions.
`projects/` is always excluded and is never removed by the packaging script.

```bash
python -m pip install pytest pytest-asyncio
python -m pytest -q
python -m compileall -q src/math_research_agent
```

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for protocol evidence and verification limits.
