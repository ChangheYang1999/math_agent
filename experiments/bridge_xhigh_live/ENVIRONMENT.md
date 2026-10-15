# Live bridge environment preparation

The bridge below is a real local installation, prepared for the existing Chrome profile. This environment preparation did not launch, quit, reload, navigate, or submit messages in any browser.

## Installed components

- Upstream: `https://github.com/DrA1ex/chatgpt-bridge.git`
- Separate checkout: `/private/tmp/mathagent-upstream-bridge`
- Source revision: `0ffdae90239988f253058c05253226152acd55d2`
- Bridge package version: `6.4.1`
- Browser extension version: `2.4.8`
- Node.js: `v24.19.0`, from the Codex bundled dependency runtime
- npm: `11.6.2`, obtained in a temporary pnpm cache because no global npm executable was available
- Actual upstream installation: `npm install --cache /private/tmp/mathagent-npm-cache --no-audit --no-fund` in the separate checkout; 138 packages installed successfully
- Actual upstream extension deployment: `npm run extension:install -- --target /private/tmp/mathagent-live-extension`
- Unpacked extension directory: `/private/tmp/mathagent-live-extension`
- The npm installation updated only `package-lock.json` in the upstream checkout. It did not change the Math Research Tree dependency tree.

## Real localhost server

- HTTP: `http://127.0.0.1:8080`
- Setup page: `http://127.0.0.1:8080/setup`
- Extension WebSocket: `ws://127.0.0.1:8080/extension/ws`
- Server PID at start: `18672`
- Tool process session: `35507`
- Isolated data directory: `/private/tmp/mathagent-bridge-live-data`
- Private local credentials: `/private/tmp/mathagent-bridge-live-data/.env`, file mode `0600`
- No credential values are included here.
- Socket inspection confirmed that the listener was bound to IPv4 `127.0.0.1:8080`, rather than a public interface.
- Server-only operation, automatic tab opening disabled, startup extension reload disabled, payload debugging disabled, answer timeout 1,200,000 ms.
- No workflow configuration was loaded. No research project was opened. No live prompt was sent during this preparation.

The server was started with these non-secret settings:

```text
HOST=127.0.0.1
PORT=8080
PUBLIC_BASE_URL=http://127.0.0.1:8080
DATA_DIR=/private/tmp/mathagent-bridge-live-data
ENV_FILE=/private/tmp/mathagent-bridge-live-data/.env
AUTO_OPEN_TAB=false
BRIDGE_STARTUP_EXTENSION_RELOAD=never
PAYLOAD_DEBUG=0
ANSWER_TIMEOUT_MS=1200000
REQUEST_MEANINGFUL_PROGRESS_TIMEOUT_MS=1200000
```

The executable arguments were `src/index.js --server --no-auto-open-tab --no-reload-extension`. This server mode does not run the interactive startup extension updater.

## Authenticated pre-connection endpoint results

These are actual localhost HTTP observations after server startup, before the extension was connected. Authorization was read directly from the private local credential file without printing it.

| Endpoint | HTTP | Observation |
| --- | --- | --- |
| `/health` | 200 | `ok=false`, `transport=extension:disconnected`, `clients=0`, no active requests or pending commands |
| `/browser/clients` | 200 | Empty client list, no selected or active client |
| `/sessions` | 500 | `No browser extension client connected. Open chatgpt.com with the ChatGPT Bridge extension enabled. Run /setup for setup instructions.` |
| `/models` | 500 | Same disconnected-client error |
| `/efforts` | 500 | Same disconnected-client error |

The first sandboxed localhost requests received `Operation not permitted`; the same read-only requests succeeded when executed with the authorized local-network escalation. This was a tool sandbox limitation rather than a bridge connectivity failure.

No mock transport, paid OpenAI API, alternate model, public tunnel, DevSpace service, or separate browser was used.
