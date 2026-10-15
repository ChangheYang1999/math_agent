# Long-prompt bridge fix

The real browser experiment passed a **20,236-character prompt**, all **four saved
Leaf Report → Parent Response pairs**, and a fresh **math/code extraction check**.
Every successful new turn verified GPT-6 / Extra High before and after, bound the
complete submitted payload to its request, and received an authoritative terminal
reply. The original Chrome instance/profile and unrelated original tab were preserved.

Exact **GPT-6 Pro was unavailable in the observed picker**. Its optional production-role
smoke is **BLOCKED**, with zero Pro requests and no substitute model. Production
model defaults and both human-approval gates remain unchanged.

## Focused changes

- [Composer patch](bridge/patches/long_prompt_v2.patch): repair MAIN/content channels,
  insert literal multiline text, verify the full editor payload, expand the new
  collapsed message, and confirm against the current DOM with complete hashes.
- [Delivery patch](bridge/patches/delivery_state.patch): preserve positive pre-Send
  cancellation evidence and prevent automatic replay of uncertain submissions.
- [Observation patch](bridge/patches/observation_recovery.patch): bind a delayed exact
  user turn using the original in-memory request boundary. This does not persist
  that boundary across a document reload.
- [Code-line patch](bridge/patches/code_lines.patch): retain CodeMirror physical
  lines, blank lines, indentation, literal whitespace, and fenced code.
- [Parent context](src/math_research_agent/parent_prompt.py): reduce the saved case
  from 13,065 to 10,988 characters while retaining its complete current report and
  3,491-character proof. Restore required prior history for replacement sessions.
- [Transport recovery](src/math_research_agent/bridge_transport.py): allow explicit
  not-submitted acknowledgement only with matching positive source/terminal proof.

The four original picker, conversation, release, and math patches remain byte-for-byte
unchanged. The [manifest](bridge/manifest.json) contains eight reviewed patch sets;
the new code-line overlay follows the original math patch using exact hash checks.
The historical failed composer candidate is excluded.

## Verified outcome and reproducibility

- Exactly one Send and one scoped expansion for the successful 20,236-character
  message; requested/submitted SHA-256 matched.
- All four original Leaf reports and the first two Parent responses remain intact.
  Both missing responses now have validated, concrete next prompts. No Leaf round
  was repeated; third-round prompts are saved and undispatched.
- Earlier sent 16k/19k diagnostics remain interrupted without accepted replies;
  neither was replayed or relabeled not sent. The first code extraction failure
  also remains immutable, separately from the final successful live check.
- 36 focused Python tests passed. Focused browser-boundary, parser, and original
  patch fixtures passed separately. These fixtures are not live inference evidence.
- A fresh pinned installation, syntax/package checks, and idempotent rerun passed.
  Follow [bridge setup](bridge/README.md); run `python3 scripts/setup_bridge.py`.

Detailed timestamps, request/conversation IDs, hashes, terminal replies, failed
attempts, and final cleanup are retained in the working copy under
`experiments/bridge_xhigh_live/RESULTS_LONG_PROMPT_FIX.md` and its run directory.
Those private experiment artifacts are omitted from this source-only package.
The loopback bridge remains running and idle at `127.0.0.1:8080`; all experimental
schedulers exited and no owned requests remain outstanding.
