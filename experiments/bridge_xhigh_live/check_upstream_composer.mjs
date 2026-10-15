// Browser-free regression for the actual modern ChatGPT pasted-text controls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const upstream = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const original = fs.readFileSync(path.join(upstream, 'tools/chrome-bridge-extension/content/composerCommands.js'), 'utf8');
const source = original.replace('      enterPrompt,', '      enterPrompt, focusAndSetComposerText, composerTextEquals,');
function fixture({ preexisting = false, ambiguous = false, wrongTail = false, replaceEditor = false, asynchronousControls = false, missingShow = false, execAccepted = false, execTruncated = false } = {}) {
  let pasted = preexisting;
  let clock = 0;
  let pastedAt = 0;
  let showClicks = 0;
  let sendClicks = 0;
  let insertions = 0;
  let execInsertions = 0;
  const approved = 'Approved Case: x_y - z.\n' + 'a'.repeat(450) + '\nEXACT_END';
  let editor;
  const control = (label, click = () => {}) => ({ disabled: false, textContent: label,
    getAttribute: (name) => name === 'aria-label' ? label : null, click });
  const remove = control('Remove pasted text attachment');
  const show = control('Show in text field', () => {
    showClicks++;
    pasted = false;
    if (replaceEditor) editor = makeEditor();
    editor.value = wrongTail ? approved.slice(0, -9) + 'BAD_END' : approved;
  });
  const send = control('Send prompt', () => sendClicks++);
  const root = { matches: () => false, querySelectorAll(selector) {
    if (selector === 'button, [role="button"]') return [...(pasted
      ? [remove, ...(!missingShow && (!asynchronousControls || clock - pastedAt >= 160) ? [show] : []), ...(ambiguous ? [show, show] : [])]
      : []), send];
    if (selector === '[data-testid="send-button"]') return editor.value ? [send] : [];
    return [];
  } };
  function makeEditor() {
    return { tagName: 'TEXTAREA', value: '', disabled: false, readOnly: false,
      focus() {}, getAttribute() { return null; }, closest: () => root,
      dispatchEvent(event) {
        if (event.type === 'paste') { insertions++; pasted = true; pastedAt = clock; this.value = ''; }
      },
    };
  }
  editor = makeEditor();
  const document = {
    querySelectorAll: (selector) => selector.startsWith('#prompt-textarea') ? [editor] : [],
    execCommand(command, _showUI, value) {
      if (command !== 'insertText') return false;
      execInsertions++;
      if (execAccepted) editor.value = value;
      if (execTruncated) editor.value = value.slice(0, 220);
      return execAccepted || execTruncated;
    },
  };
  class FakeEvent { constructor(type, details) { this.type = type; Object.assign(this, details); } }
  const context = vm.createContext({ console, document, window: {}, Date: class extends Date { static now() { return clock; } },
    DataTransfer: class { setData() {} }, ClipboardEvent: FakeEvent, InputEvent: FakeEvent, Event: FakeEvent });
  context.globalThis = context;
  vm.runInContext(source, context);
  const commands = context.ChatGptComposerCommands.createComposerCommands({
    delay: async (ms) => { clock += ms; }, diagnostic: () => {}, visibleText: (node) => node.value || node.textContent || '',
    isVisible: () => true, isPrimaryChatSurfaceElement: () => true,
  });
  return { commands, approved, editor: () => editor,
    counts: () => ({ showClicks, sendClicks, insertions, execInsertions }) };
}

const plain = fixture({ execAccepted: true });
const plainPrepared = await plain.commands.focusAndSetComposerText(plain.editor(), plain.approved, { requestId: 'plain-long-prompt' });
assert.equal(plainPrepared.method, 'exec_command');
assert.equal(plainPrepared.element.value, plain.approved);
assert.deepEqual(plain.counts(), { showClicks: 0, sendClicks: 0, insertions: 0, execInsertions: 1 }, 'verified ordinary insertion must skip paste entirely');

const fallback = fixture({ execTruncated: true });
const fallbackPrepared = await fallback.commands.focusAndSetComposerText(fallback.editor(), fallback.approved, { requestId: 'setter-fallback' });
assert.equal(fallbackPrepared.method, 'paste', 'unverified ordinary insertion must fall through to existing paste recovery');
assert.equal(fallbackPrepared.element.value, fallback.approved);
assert.deepEqual(fallback.counts(), { showClicks: 1, sendClicks: 0, insertions: 1, execInsertions: 1 });

const normal = fixture({ replaceEditor: true, asynchronousControls: true });
const oldEditor = normal.editor();
const prepared = await normal.commands.focusAndSetComposerText(oldEditor, normal.approved, { requestId: 'own-long-prompt' });
assert.notEqual(prepared.element, oldEditor, 'React replacement editor must be reacquired');
assert.equal(prepared.element.value, normal.approved);
assert.equal(normal.counts().showClicks, 1);
assert.equal(normal.counts().sendClicks, 0, 'preparation must never invoke Send');
assert.equal(normal.counts().insertions, 1);
assert.ok(prepared.button, 'normal bridge submit receives its ready button');
assert.equal(normal.commands.composerTextEquals({ value: normal.approved.slice(0, 220) }, normal.approved), false);
assert.equal(normal.commands.composerTextEquals({ value: normal.approved.toLowerCase() }, normal.approved), false);
assert.equal(normal.commands.composerTextEquals({ value: normal.approved.replace('x_y', 'xy') }, normal.approved), false);

for (const scenario of [{ preexisting: true }, { ambiguous: true }, { wrongTail: true }, { missingShow: true }]) {
  const test = fixture(scenario);
  await assert.rejects(test.commands.focusAndSetComposerText(test.editor(), test.approved, { requestId: 'must-not-send' }),
    (error) => error.code === 'COMPOSER_TEXT_VERIFY_FAILED' && error.provenNotExecuted === true
      && error.cancellationEvidence.reason === 'submission_boundary_not_entered');
  assert.equal(test.counts().sendClicks, 0);
  if (scenario.preexisting) {
    assert.equal(test.counts().showClicks, 0, 'never absorb pre-existing user attachment');
    assert.equal(test.counts().insertions, 0);
  }
  if (scenario.ambiguous) assert.equal(test.counts().showClicks, 0, 'ambiguous controls must not be clicked');
  if (scenario.missingShow) assert.equal(test.counts().showClicks, 0, 'incomplete controls must time out before any click');
}
console.log('PASS: verified plain-text insertion skips paste; truncated insertion falls through safely; asynchronous own-paste unwrap/full text/replaced editor/untouched Send; pre-existing/ambiguous/wrong-tail/incomplete refusal');
