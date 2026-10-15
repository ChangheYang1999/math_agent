# Implementation notes — 0.2.1

This is an incremental update to the Research Tree. Existing nodes, immutable round history,
P0 checkpoints, approval hashes, fake/manual transports, and hierarchical report sections remain.
SQLite schema 1 upgrades transactionally to schema 2: bridge session/turn identifiers and ordered
`review_messages` are added; existing research and configuration rows are preserved.

Changes:

- `bridge_transport.py`: asynchronous browser-backed adapter and read-only diagnostics.
- `scheduler.py`, `schemas.py`, and two discussion/display templates: Ask Parent is advice only;
  explicit Request Revision retains the versioned prompt/correction protocol. English/Chinese
  boundary translation preserves explicit math spans. Discussion cannot modify research state.
- `store.py`, `config.py`, and research templates: weighted allocations are upper capacity limits;
  unused capacity is normal, splits respect caps, contraction waits for safe round boundaries.
- P1 failures remain visible and non-blocking; only pending conflicting control actions delay a leaf.
- `dashboard.py`, dashboard HTML, and `cli.py`: four distinct review controls, persistent bilingual
  history, actual bridge diagnostics and binding details, and uncertain-turn visibility.
- Packaging/configuration/docs: minimal httpx dependency; explicit source allowlists; obsolete code,
  duplicate environments, old builds and historical test copies removed. User projects are retained.

## Upstream protocol evidence

Both requested upstreams were inspected. [Zhenyu98/codex-chatgpt-bridge](https://github.com/Zhenyu98/codex-chatgpt-bridge)
provides DevSpace/MCP and task/controller machinery, rather than the browser send/receive protocol
needed here. No DevSpace, tunnel, OAuth service, extension bundle, or upstream checkout is included.

The adapter was checked against DrA1ex/chatgpt-bridge commit
[`0ffdae90239988f253058c05253226152acd55d2`](https://github.com/DrA1ex/chatgpt-bridge/tree/0ffdae90239988f253058c05253226152acd55d2).
README, getting-started, API and extension docs were read along with actual server/extension code:

- [`routes.js`](https://github.com/DrA1ex/chatgpt-bridge/blob/0ffdae90239988f253058c05253226152acd55d2/src/routes.js)
  defines authenticated HTTP endpoints and durable turn lookup/events. The adapter uses
  `POST /turns`, `GET /turns/:id`, and `GET /turns/:id/events?stream=1`, since the direct
  `/sessions/:id/messages` route does not provide durable result recovery.
- [`turnManager.js`](https://github.com/DrA1ex/chatgpt-bridge/blob/0ffdae90239988f253058c05253226152acd55d2/src/turnManager.js)
  persists caller-supplied IDs and idempotency keys, forwards exact message content and strict
  `sourceClientId`, and stores the terminal full `output.response`. The adapter still never
  replays an ambiguous POST: it queries that original durable ID or holds UNCERTAIN.
- [`publicTurnStream.js`](https://github.com/DrA1ex/chatgpt-bridge/blob/0ffdae90239988f253058c05253226152acd55d2/src/http/publicTurnStream.js)
  emits named SSE frames and terminal `turn/completed` / failed events. Streaming fragments are
  ignored; the authoritative stored terminal response is retrieved before returning text.
- [`requestPreparation.js`](https://github.com/DrA1ex/chatgpt-bridge/blob/0ffdae90239988f253058c05253226152acd55d2/tools/chrome-bridge-extension/content/requestPreparation.js)
  proves empty model/effort selectors do not change pickers. Its selection path uses fuzzy matching,
  which can confuse High with Extra High. This adapter instead requires the operator's exact
  initial selection, checks that bound tab before and after the turn, and stores desired model/effort
  separately in local bindings and upstream metadata. It never trusts fuzzy success flags.

Each active node has a unique bound tab/conversation. Role promotion or rollover preserves old
bindings. Turn identifiers, attempted sends, terminal answers, and model-verification failures remain
durable. A detected model drift requires explicit manual reconciliation; restoring the current
picker alone cannot make a prior uncertain result authoritative. Ordinary bridge disconnects can
resume the same stored turn. Token values come only from the environment, not SQLite/YAML.

## Verification and limits

- `python -m pytest -q`: 26 focused tests pass, including five mock HTTP/SSE bridge tests.
- Python compilation, Ruff lint/format, JavaScript syntax, editable install and clean package builds
  are checked separately during delivery.
- Fake two-round CLI and review ON/OFF tests verify linked reports, parent responses and next prompts.
- Browser/HTTP dashboard checks verify two questions before approval, retained exact hash/version,
  refresh persistence, revised prompt approval, Later, and subsequent report approval.
- Existing-project migration tests compare research records and conversation bindings before/after.

Real-web testing was limited to a read-only request to `127.0.0.1:8080/health`, which refused connection.
No real ChatGPT conversation was created, no requested model/effort was validated against a logged-in
account, and no real research message was sent or received. The remaining prerequisite is a compatible
running bridge, connected Chrome extension, normal login and required model access. New tab/model
configuration remains manual because upstream picker automation is not sufficiently exact.
Browser notifications remain permission-dependent. Legacy `state.db` projects are preserved without
conversion. This tool does not independently prove mathematical claims.
