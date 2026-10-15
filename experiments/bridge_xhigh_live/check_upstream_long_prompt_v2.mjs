// Paired actual MAIN/content composer modules, not a stubbed successful setter.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { webcrypto, createHash } from 'node:crypto';

const upstream = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const composerFile = path.join(upstream, 'tools/chrome-bridge-extension/content/composerCommands.js');
const mainFile = path.join(upstream, 'tools/chrome-bridge-extension/artifactCaptureMain.js');
const source = fs.readFileSync(composerFile, 'utf8').replace('      enterPrompt,',
  '      enterPrompt, focusAndSetComposerText, composerTextEquals, pastedTextControls,');
const mainSource = fs.readFileSync(mainFile, 'utf8');
const prompt = 'LONG_BEGIN_93A\nLiteral <tag> & <br> must remain text.\n' + ('Preserve x_y, X-Y, \\sqrt{2}, a^2, spaces  and punctuation.\n'.repeat(245)) + 'LONG_END_7FC';
assert.ok(prompt.length >= 13065);

function fixture({ native = true, missingShow = false, preexisting = false, send = 'confirm', collapseUser = false, asyncExpansion = false } = {}) {
  let clock = 0, editorText = '', editorNodes = [], ready = false, pasted = preexisting, pasteAt = 0;
  let nativeCalls = 0, pastes = 0, showClicks = 0, sends = 0;
  let userExpansions = 0;
  const diagnostics = [], chatEvents = [], turns = [], messages = [], observedRoots = [], listeners = new Set();
  let editor;
  const control = (label, click = () => {}, decorated = false) => ({
    disabled: false, isConnected: true, textContent: decorated ? 'DECORATIVE_SVG_TITLE' + label : label,
    innerText: label, getAttribute: (name) => name === 'aria-label' && !decorated ? label : null,
    cloneNode() { return { textContent: label, querySelectorAll: () => [] }; }, click,
  });
  const remove = control('Remove pasted text attachment');
  const show = control('Show in text field', () => {
    showClicks++; pasted = false;
    editor = makeEditor(); // React replaces the editor when expanding the chip.
    editorText = prompt; ready = true;
  }, true);
  const sendButton = control('Send prompt', () => {
    sends++;
    if (send === 'confirm' || send === 'wrong-tail') {
      const body = send === 'wrong-tail' ? prompt.slice(0, -12) + 'WRONG_END' : prompt;
      const payload = { textContent: collapseUser ? body.slice(0, 10240) : body };
      const more = control('Show more', () => {
        userExpansions++;
        if (asyncExpansion) setTimeout(() => {
          main.isConnected = false;
          main = { isConnected: true }; // React replaces the root; the old observer receives no mutation.
          payload.textContent = body;
        }, 5);
        else payload.textContent = body;
      });
      const bubble = { textContent: body + '\n…\nShow more',
        querySelectorAll: (selector) => selector === '.whitespace-pre-wrap[dir="auto"]' ? [payload]
          : selector === 'button, [role="button"]' && collapseUser ? [more] : [] };
      turns.push({ key: 'own-new-user', textContent: 'You said\n' + body + '\nCopy',
        querySelector: (selector) => selector === '[data-user-message-bubble="true"]' ? bubble : null });
      editorText = ''; editorNodes = []; ready = false;
    }
  });
  let main = { isConnected: true };
  const root = { tagName: 'FORM', matches: () => false, querySelectorAll(selector) {
    if (selector === 'button, [role="button"]') return [
      ...(pasted ? [remove, ...(!missingShow && clock - pasteAt >= 160 ? [show] : [])] : []),
      ...(ready ? [sendButton] : []),
    ];
    if (selector === '[data-testid="send-button"]') return ready ? [sendButton] : [];
    return [];
  } };
  function makeEditor() {
    return { tagName: 'DIV', isContentEditable: true, isConnected: true,
      disabled: false, readOnly: false, children: [],
      get childNodes() { return editorNodes; },
      get innerText() { return editorText; }, get textContent() { return editorNodes.length ? editorNodes.map((node) => node.textContent).join('') : editorText; },
      set textContent(value) { editorText = value; editorNodes = []; }, focus() {},
      getClientRects: () => [{ width: 600, height: 150 }],
      getAttribute: (name) => name === 'contenteditable' ? 'true' : null,
      closest: (selector) => selector === 'form' ? root : selector.includes('main') ? main : null,
      querySelector: () => ({ set textContent(value) { editorText = value; } }),
      dispatchEvent(event) {
        if (event.type === 'paste') { pastes++; pasted = true; pasteAt = clock; editorText = ''; editorNodes = []; ready = false; }
      },
    };
  }
  editor = makeEditor();
  const document = { body: main, documentElement: main,
    querySelectorAll: (selector) => selector.includes('#prompt-textarea') ? [editor] : [],
    createRange: () => ({ selectNodeContents() {}, collapse() {} }),
    execCommand(command, _ui, value) {
      if (command === 'delete') { editorText = ''; editorNodes = []; ready = false; return true; }
      if (command !== 'insertText' && command !== 'insertHTML') return false;
      nativeCalls++;
      if (native) {
        if (command === 'insertHTML') {
          const html = value.match(/^<span data-prompt-literal-paste="">([\s\S]*)<\/span>$/)?.[1];
          assert.ok(html, 'multiline path uses the observed literal-paste span');
          const lines = html.split('<br>').map((text) => text.replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&'));
          editorText = lines.join('\n');
          const nodes = lines.flatMap((text, index) => [...(index ? [dom('BR', [])] : []), { nodeType: 3, textContent: text }]);
          editorNodes = [dom('P', [dom('SPAN', nodes)])];
        } else { editorText = value; editorNodes = []; }
        ready = true;
      }
      return native;
    },
  };
  class FakeEvent { constructor(type, details) { this.type = type; Object.assign(this, details); } }
  const window = {
    getComputedStyle: () => ({ display: 'block', visibility: 'visible', opacity: '1' }),
    getSelection: () => ({ removeAllRanges() {}, addRange() {} }),
    addEventListener: (type, fn) => { if (type === 'message') listeners.add(fn); },
    removeEventListener: (type, fn) => { if (type === 'message') listeners.delete(fn); },
    postMessage(data) { messages.push(data); queueMicrotask(() => {
      for (const fn of [...listeners]) fn({ source: window, data });
    }); },
  };
  const context = vm.createContext({ console, document, window, TextEncoder, crypto: webcrypto,
    Date: class extends Date { static now() { return clock; } },
    setTimeout: (fn, ms) => setTimeout(fn, ms === 1000 ? (asyncExpansion ? 800 : 0) : ms), clearTimeout,
    MutationObserver: class { observe(root) { observedRoots.push(root); } disconnect() {} },
    DataTransfer: class { setData() {} }, ClipboardEvent: FakeEvent, InputEvent: FakeEvent, Event: FakeEvent,
  });
  context.globalThis = context;
  vm.runInContext(mainSource.slice(mainSource.indexOf('// The composer helper must share')), context);
  vm.runInContext(source, context);
  const commands = context.ChatGptComposerCommands.createComposerCommands({
    CONFIG: { promptSubmitAckTimeoutMs: 1000 },
    delay: async (ms) => { clock += ms; },
    diagnostic: (type, data) => diagnostics.push({ type, ...data }),
    emitChatEvent: (_request, type, data) => chatEvents.push({ type, ...data }),
    visibleText: (node) => node?.innerText ?? node?.textContent ?? '',
    isVisible: () => true, isPrimaryChatSurfaceElement: () => true,
    getTurnNodes: () => turns, turnKey: (turn) => turn.key, turnRole: () => 'user',
    waitForChatPageReady: async () => {}, isGenerating: () => false,
  });
  return { commands, diagnostics, chatEvents, messages, turns, observedRoots, editor: () => editor,
    userExpansions: () => userExpansions,
    counts: () => ({ nativeCalls, pastes, showClicks, sends }), request: { requestId: 'own-fixture-request', options: {} } };
}

function dom(tagName, childNodes) {
  return { nodeType: 1, tagName, childNodes,
    get textContent() { return childNodes.map((node) => node.textContent || '').join(''); },
    get innerText() { return tagName === 'BR' ? '\n' : childNodes.map((node) => node.innerText ?? node.textContent ?? '').join(''); } };
}

const paired = fixture();
const prepared = await paired.commands.focusAndSetComposerText(paired.editor(), prompt, paired.request);
assert.equal(prepared.method, 'page_main', 'the actual paired MAIN-world channel must succeed');
assert.equal(prepared.element.innerText, prompt);
assert.deepEqual(paired.counts(), { nativeCalls: 1, pastes: 0, showClicks: 0, sends: 0 });
assert.equal(paired.messages[0].source, 'chatgpt-browser-bridge-composer-content-v1');
assert.equal(paired.messages[1].source, 'chatgpt-browser-bridge-composer-main-v1');
assert.equal(paired.messages[1].result.ok, true);
assert.equal(paired.messages[1].result.textLength, prompt.length);
assert.equal(paired.messages[1].result.setMethod, 'insertHTML');
assert.equal(paired.messages[1].result.beforeFallback.logicalNewlines, (prompt.match(/\n/g) || []).length);
const paragraphs = { tagName: 'DIV', childNodes: [dom('P', [{ nodeType: 3, textContent: 'LINE-ONE' }]),
  dom('P', [{ nodeType: 3, textContent: 'LINE-TWO' }])], innerText: 'LINE-ONE\n\nLINE-TWO' };
assert.equal(paired.commands.composerTextEquals(paragraphs, 'LINE-ONE\nLINE-TWO'), true, 'block layout does not insert a false extra payload newline');
assert.equal(paired.commands.composerTextEquals({ innerText: prompt.slice(0, 200) }, prompt), false);

const complete = fixture();
const evidence = await complete.commands.enterPrompt(prompt, complete.request);
assert.equal(evidence.reason, 'new_user_turn');
assert.equal(evidence.fullPromptTextMatch, true);
assert.equal(evidence.expectedCharacters, prompt.length);
assert.equal(evidence.observedCharacters, prompt.length, 'checksum scopes the actual observed user-message bubble');
assert.equal(evidence.observedSha256, createHash('sha256').update(prompt).digest('hex'));
assert.equal(evidence.observedSha256, evidence.expectedSha256);
assert.equal(complete.counts().sends, 1);

const collapsed = fixture({ collapseUser: true });
const expandedEvidence = await collapsed.commands.enterPrompt(prompt, collapsed.request);
assert.equal(expandedEvidence.observedCharacters, prompt.length);
assert.equal(expandedEvidence.observedSha256, expandedEvidence.expectedSha256);
assert.equal(collapsed.userExpansions(), 1, 'only the matching newly submitted truncated user turn is expanded');
assert.equal(collapsed.counts().sends, 1, 'user-turn expansion never repeats Send');

const rootReplaced = fixture({ collapseUser: true, asyncExpansion: true });
const rootReplacedEvidence = await rootReplaced.commands.enterPrompt(prompt, rootReplaced.request);
assert.equal(rootReplaced.observedRoots[0].isConnected, false, 'fixture disconnects the original observation root');
assert.equal(rootReplacedEvidence.fullPromptTextMatch, true);
assert.equal(rootReplacedEvidence.observedSha256, createHash('sha256').update(prompt).digest('hex'));
assert.equal(rootReplacedEvidence.observedSha256, rootReplacedEvidence.expectedSha256);
assert.equal(rootReplaced.userExpansions(), 1);
assert.equal(rootReplaced.counts().sends, 1, 'async expansion/root replacement is acknowledged without another Send');

for (const options of [{ send: 'uncertain' }, { send: 'wrong-tail' }, { send: 'wrong-tail', collapseUser: true }]) {
  const uncertain = fixture(options);
  await assert.rejects(uncertain.commands.enterPrompt(prompt, uncertain.request),
    (error) => error.code === 'PROMPT_SUBMIT_UNCERTAIN' && error.provenNotExecuted !== true);
  assert.equal(uncertain.counts().sends, 1, 'missing proof never replays the submission');
  assert.equal(uncertain.chatEvents.at(-1).type, 'prompt.submit.uncertain');
}

const fallback = fixture({ native: false });
const expanded = await fallback.commands.focusAndSetComposerText(fallback.editor(), prompt, fallback.request);
assert.equal(expanded.method, 'paste');
assert.equal(expanded.element.innerText, prompt);
assert.equal(fallback.counts().showClicks, 1, 'semantic control name ignores decorative SVG text');
assert.equal(fallback.counts().sends, 0);

for (const options of [{ native: false, missingShow: true }, { preexisting: true }]) {
  const blocked = fixture(options);
  await assert.rejects(blocked.commands.focusAndSetComposerText(blocked.editor(), prompt, blocked.request),
    (error) => error.code === 'COMPOSER_TEXT_VERIFY_FAILED' && error.provenNotExecuted === true
      && error.cancellationEvidence.reason === 'submission_boundary_not_entered');
  assert.equal(blocked.counts().sends, 0);
}
const empty = fixture();
assert.equal(empty.commands.promptSubmissionEvidence(empty.request, new Set(), prompt, { textContent: prompt }).confirmed, false);
console.log(`PASS: ${prompt.length}-character actual MAIN/content handshake, full observed-user SHA256, async Show more/root-replacement acknowledgement with exactly one Send, strict uncertainty, semantic long-paste fallback and explicit NOT_SENT guards.`);
