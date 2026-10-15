# Reproducible local browser bridge

This project uses the third-party [DrA1ex/chatgpt-bridge](https://github.com/DrA1ex/chatgpt-bridge),
not an officially supported OpenAI API integration. The reviewed upstream revision is
`0ffdae90239988f253058c05253226152acd55d2` (bridge 6.4.1, extension 2.4.8).
Use an authorized account and respect the applicable service terms.

## Install or update

From the Math Research Tree project, run:

```sh
python3 scripts/setup_bridge.py
```

The installer clones a separate checkout at
`~/.local/share/math-research-agent/chatgpt-bridge`, checks the exact revision and
source hashes, and applies only reviewed patches that are not already present.
It installs the pinned lockfile dependencies with `npm ci`, runs upstream's syntax
and package-content checks, and publishes the unpacked extension at
`~/.local/share/math-research-agent/extension`. It never starts/reloads a browser
or server, changes a browser profile, reads credentials, or sends messages.
Node.js 20+ and npm are required. When available, the Codex bundled Node/pnpm
runtime can bootstrap pinned npm 11.6.2 into a separate local cache.

Use `--checkout PATH --extension-dir PATH` for another separate installation.
An existing checkout at another revision, unexpected tracked edit, partially
applied patch, or changed accepted file is rejected without resetting it.
An incremental overlay must follow its declared prior patch: every before/after
hash must form the exact accepted chain. Known final hashes identify earlier
patches as applied; unknown edits or a different chain are refused.
The installation is repeatable; applied patches are verified and skipped.
`--check-only` verifies an existing checkout without changing it;
`--source-only` applies patches and checks JavaScript syntax without installing
dependencies or publishing the extension. The latter is intended for offline
source preparation after a checkout is already available.

## Accepted patches

`manifest.json` records each patch checksum and the exact base/patched source
hashes. The four baseline patches remain byte for byte unchanged. Three
additional patch sets were accepted after an intact 20,236-character live GPT-6
Extra High request received a matching authoritative terminal reply. These eight
previously live-verified sets remain unchanged. Phase 3 adds one small
**offline-verified** recovery-role patch. Consolidated debugging deploys that
ninth set through this same recipe; loading it requires the existing extension's
normal Chrome Reload action. File installation alone does not prove live recovery.
A tenth, **offline-verified** final-content selector fix addresses the real Pro
smoke failure where a separate reasoning recap was captured as the answer. Its
installation does not prove a post-fix live pass.
The recipe reproduces all eleven:

| Patch | Observed behavior addressed |
| --- | --- |
| `picker.patch` | Read the actual checked model and exact Extra High slider tier; distinguish High and unknown tiers. |
| `conversation.patch` | Promote a temporary conversation UUID to its persistent ID only with matching request and user-turn anchors. |
| `release.patch` | Settle reconciliation commands so a completed request can prove cleanup and release its own lease. |
| `math.patch` | Preserve KaTeX source notation while extracting prose; retain literal inline/fenced code and the original DOM. |
| `long_prompt_v2.patch` | Correct the MAIN/content message channel, preserve multiline literal input, handle observed pasted-text controls, and confirm the complete new user turn. |
| `delivery_state.patch` | Preserve explicit pre-Send non-execution proof through durable terminal errors; prohibit automatic replay after uncertain Send. Includes the updated upstream delivery/acknowledgement tests. |
| `observation_recovery.patch` | Reconcile delayed user-turn anchors against the full saved payload and original new-turn boundary. |
| `code_lines.patch` | Incremental overlay after `math.patch`: preserve physical CodeMirror lines, indentation, blank lines, and code fences. The original math patch remains unchanged. |
| `resume_roles.patch` | Offline verification and consolidated deployment: use the existing current-turn DOM role helper during request resumption, preventing a keyed user turn from being misclassified as missing. Exact key/text matching and refusal to replay remain unchanged. |
| `final_answer.patch` | Select explicit final assistant content within the same keyed turn and marker interval; reject a recap-only activity header while preserving legacy branches. Offline verified against the captured Pro DOM; deployment and live retest remain separate. |
| `picker_activation.patch` | Before model/effort discovery, activate only the existing connected target tab. Pass the existing cancellation signal through picker waits so timed-out reads cannot leave stale clicks or menu cleanup. Offline verification passed; deployment and live checks are recorded separately. |

The failed historical `experiments/bridge_xhigh_live/upstream_composer.patch`
remains diagnostic evidence and is excluded from this recipe. It is distinct
from the accepted `long_prompt_v2.patch`; synthetic fixture results alone were
not used to accept that fix. The manifest now requires the exact live-tested
composer source hash and rejects another candidate or unreviewed edit. Detailed
private test records remain in the local experiment directory, outside the
source package. A direct transport pass and complete Research Tree execution
are reported separately in those records.

The compact browser-free extraction regression ships with this recipe. It loads
the actual shared/content parser pair and checks physical lines, empty lines,
indentation, literal whitespace, fences, and an unchanged source DOM:

```sh
node bridge/tests/code_lines.mjs
# Or specify another already installed checkout:
node bridge/tests/code_lines.mjs /path/to/chatgpt-bridge
```

The default checkout is the same persistent directory used by the installer.
These fixture checks send no messages and are separate from the recorded live
math/code pass.

The separate recovery fixture loads the actual current-turn DOM helper and
request-resume code. It reproduces the legacy-role failure before the patch,
checks exact boundary recovery afterward, and retains missing-boundary refusal,
legacy matching and zero Send actions:

```sh
node bridge/tests/resume_roles.mjs /path/to/reviewed-chatgpt-bridge
```

This fixture is **OFFLINE_PASS**, separate from deployment and live recovery
evidence. It does not adopt or
rewrite a historical failed terminal reply, and installing source does not
authorize replay of an uncertain request.

## Start and stop the localhost server

Do not start a second server on the same port. Stop active disposable workloads
and reconcile uncertain requests before changing an existing installation.
Start in a foreground terminal:

```sh
cd ~/.local/share/math-research-agent/chatgpt-bridge
HOST=127.0.0.1 PORT=8080 PUBLIC_BASE_URL=http://127.0.0.1:8080 \
AUTO_OPEN_TAB=false BRIDGE_STARTUP_EXTENSION_RELOAD=never PAYLOAD_DEBUG=0 \
node src/index.js --server --no-auto-open-tab --no-reload-extension
```

Stop this foreground server with **Ctrl+C** after the research scheduler is
stopped and its requests are terminal. The upstream default private data and
credential file is `~/.bridge-data/.env`; preserve that directory across restarts.
To reuse a different existing installation's data, supply its `DATA_DIR` and
`ENV_FILE` explicitly. This recipe never copies local credentials into source.
No public endpoint or tunnel is needed.

## Connect or update the same Chrome profile

Keep the currently open Chrome browser and logged-in profile. Preserve existing
conversations; perform setup in a new tab.

1. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**,
   and select `~/.local/share/math-research-agent/extension`.
2. For updates to that same directory, use the extension's **Reload** button
   only after all owned requests are terminal. Refresh a disposable ChatGPT
   setup/test tab if its content script still uses the old runtime. Do not
   reload an unrelated original conversation.
3. Open `http://127.0.0.1:8080/setup` in a new tab. Click **Copy** beside the
   masked **Bridge token** field. Never include that value in a report.
4. Open a new `https://chatgpt.com/` tab. Click the **ChatGPT Bridge toolbar
   action** (through Chrome's extension menu if unpinned) to show its setup
   panel. The baseline runtime may not display a floating button before its
   first connection. Paste the token into the masked field and choose
   **Save & connect**. Retain the loopback server URL.
5. Check the setup page for a compatible connected tab. The extension uses
   **BRIDGE_TOKEN**; Python clients use the separate private **API_TOKEN** via
   `MATHAGENT_BRIDGE_API_TOKEN`. Neither token belongs in project configuration.

Exact model/effort verification remains mandatory before and after each real
turn. Each concurrent request must target its distinct `sourceClientId`; unbound
requests use an exclusive upstream queue. Do not automatically resend a request
whose submission is uncertain.

## Clean source package

From the Math Research Tree project:

```sh
python3 scripts/package_source.py /tmp/math-agent-source.zip
```

The explicit allowlist includes this setup recipe, accepted patches/manifest,
project source, templates, tests, and the compact fix summary when available.
It excludes research databases, detailed live experiment records/conversations,
private configuration, environments, caches, historical code, and the separate
third-party checkout and its dependencies.

The Pro final-content fixture reproduces the 17-character recap before the fix,
checks selection of the exact final assistant DOM afterward, and refuses a
recap without a final answer. It also checks current keyed and legacy layouts without sending:

```sh
node bridge/tests/final_answer.mjs /path/to/chatgpt-bridge
```

Selector verification and content fidelity are separate. The captured Pro reply
passes final-node selection, but **plain-Markdown fidelity is KNOWN_FAIL**: the
existing Markdown renderer converts two source underscore emphasis delimiters
inside a JSON evidence string into stars. Valid JSON alone is not lossless
mathematical evidence. Preserve the original terminal and use authenticated,
source-bound canonical final JSON for audited recovery; never guess delimiter
repairs from rendered text. A post-deployment read may prove selector behavior
while still failing this exact content comparison.

After the user reloaded the same installed extension, a read-only recovery from
the already completed owned Pro Leaf returned the full 4,426-character final
JSON instead of the 17-character reasoning recap: **LIVE_SELECTOR_RECOVERY_PASS**.
The original upstream terminal was preserved. This confirms live selector
extraction only; the plain-Markdown fidelity failure above remains, and it is
not a normal post-fix inference test. The ninth `request.resume` handler has
not been exercised live and remains **NOT_RUN**. Future generated response
instructions use a fenced JSON block to protect literal mathematical strings;
that prevention is separate from recovery of the historical plain response.

The picker-activation fixture uses the actual background forwarding and picker
helpers with deterministic storage/clock/Chrome stubs. It reproduces missing
activation and ignored cancellation before the patch, checks only the connected
existing tab is activated for model/effort reads, and checks that aborted waits
clear their timer and perform no later UI work:

```sh
node bridge/tests/picker_activation.mjs /path/to/chatgpt-bridge
```

This is an offline fixture, not a browser inference result. It adds no HTTP
route or cancellation registry and never changes a tab URL, creates a tab or
reloads an existing tab. The original ten patch files remain unchanged.

The eleventh update later passed all six actual family/tier discovery reads on
the three owned experiment tabs after their page refreshes. The supported
maintenance reload API had returned a reconnect timeout; that result is not a
reload success or a third user-confirmed reload. A subsequent fenced Pro output
matched canonical JSON field values exactly, while its submission evidence failed
because the instruction itself used rendered inline-code delimiters. Future
templates now use plain “fenced JSON code block” wording. Boundary checks remain
strict; no previously submitted prompt is resent or retroactively rewritten.

The twelfth overlay handles the current rich user-message payload. It prefers
the unique `[data-markdown-text-tone="user-message"]` inside the user bubble,
excluding sibling ellipsis and Show more/less controls. The previous literal
payload fallback and full submitted-text check remain unchanged. An offline
replay of the captured 19,178-character prompt reproduces the old failure,
checks exact text/hash after expansion, and refuses wrong prefixes, wrong tails,
existing turns and assistant turns:

```sh
node bridge/tests/user_payload.mjs /path/to/chatgpt-bridge
```

All twelve reviewed patches were published to the same existing extension
folder. The pending experimental page was retained through its natural terminal;
the later supported maintenance update completed successfully with no active
Bridge requests. A subsequent actual rich user-message request automatically
expanded 10,207 displayed characters to the exact 23,768-character input, confirmed
one Send with matching full SHA-256, and completed normally:
**LIVE_RICH_PAYLOAD_DELIVERY_PASS**. This is separate from the historical failed
terminal and from patch9 request.resume, whose live handler remains **NOT_RUN**.
