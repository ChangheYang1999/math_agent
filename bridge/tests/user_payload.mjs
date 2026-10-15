// Offline replay of rich user payloads and strict full-prompt delivery checks.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const root = path.resolve(process.argv[2]);
const captureDir = process.argv[3] && path.resolve(process.argv[3]);
const { parseCapturedHtml } = await import(pathToFileURL(path.join(root, 'test/helpers/offlineChatDom.js')));
const manifest = JSON.parse(fs.readFileSync(path.join(packageRoot, 'bridge/manifest.json'), 'utf8'));
const patch = manifest.accepted_patches.find((p) => p.name === 'user_payload');
const sha = (value) => createHash('sha256').update(value).digest('hex');
const richSelector = '[data-markdown-text-tone="user-message"]';
const composerPath = 'tools/chrome-bridge-extension/content/composerCommands.js';
const userPath = 'tools/chrome-bridge-extension/content/userTurnState.js';
const composerAfter = fs.readFileSync(path.join(root, composerPath), 'utf8');
const userAfter = fs.readFileSync(path.join(root, userPath), 'utf8');
// Reconstruct the exact reviewed predecessor, never edit the checkout.
const composerBefore = composerAfter.replace('  const rich = Array.from(bubble?.querySelectorAll?.(\'[data-markdown-text-tone="user-message"]\') || []);\n  if (rich.length === 1) return visibleText(rich[0]);\n', '');
const userBefore = userAfter.replace('      const rich = Array.from(bubble?.querySelectorAll?.(\'[data-markdown-text-tone="user-message"]\') || []);\n      if (rich.length === 1) return rich[0];\n', '');
for (const [name, source] of [[composerPath, composerBefore], [userPath, userBefore]]) {
  assert.equal(sha(source), patch.files.find((f) => f.path === name).base_sha256, 'before source is the exact eleven-patch predecessor');
}
const render = (node) => node.nodeType === 3 ? node.textContent
  : node.tagName === 'BR' ? '\n' : Array.from(node.childNodes || [], render).join('');
const escape = (text) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const raw = 'Exact research input.\n\nKeep literal TeX \\alpha, x_j, stars * and words Show less.\nFull mathematical evidence.';
const prefix = raw.slice(0, 54);
const bubble = (text, expanded) => `<div data-user-message-bubble="true"><div class="whitespace-pre-wrap"><div data-markdown-text-tone="user-message" dir="auto">${escape(text).replaceAll('\n', '<br>')}</div></div>${expanded ? '' : '<span aria-hidden="true">…</span>'}<button aria-expanded="${expanded}" data-thread-find-skip="true" data-markdown-copy="exclude">${expanded ? 'Show less' : 'Show more'}</button></div>`;

function fixture(composerSource, userSource, collapsed, expanded, expected, { baseline = false, role = 'user' } = {}) {
  const turn = parseCapturedHtml(`<section data-message-author-role="user">${collapsed.html}</section>`);
  let nativeText = collapsed.text;
  let clicks = 0;
  const visibleText = (node) => {
    const rich = node?.matches?.(richSelector) ? node : node?.querySelector?.(richSelector);
    // Captured browser innerText is authoritative for the chrome-contaminated
    // ancestor. Rich content itself is replayed from actual HTML spans/br nodes.
    if (rich && node !== rich && node.querySelector?.('button')) return nativeText;
    return render(node);
  };
  const context = vm.createContext({ console, document: { body: turn }, location: { href: 'https://chatgpt.com/c/offline-owned' } });
  vm.runInContext(composerSource, context);
  vm.runInContext(userSource, context);
  const deps = { CONFIG: {}, DOM_PARSER: {}, visibleText, normalizeText: (v) => String(v).trim(), normalizeComparable: (v) => String(v).trim(), isVisible: () => true, isPrimaryChatSurfaceElement: () => true, getTurnNodes: () => [turn], turnRole: () => role, turnKey: () => 'own-user', diagnostic() {} };
  const api = context.ChatGptComposerCommands.createComposerCommands(deps);
  const state = context.ChatGptUserTurnState.createUserTurnState(deps);
  const control = turn.querySelector('button[aria-expanded="false"]');
  if (control) control.click = () => {
    clicks += 1;
    const replacement = parseCapturedHtml(`<section>${expanded.html}</section>`);
    turn.childNodes = [];
    for (const child of [...replacement.childNodes]) turn.append(child);
    nativeText = expanded.text;
  };
  const initial = state.readUserTurnPromptText(turn);
  const result = api.promptSubmissionEvidence({ requestId: 'offline-original' }, new Set(baseline ? ['own-user'] : []), expected, null, { requireUserTurn: true, allowExpand: true, expandedTurnKeys: new Set() });
  return { result, clicks, initial, final: state.readUserTurnPromptText(turn) };
}

function check(collapsed, expanded, expected) {
  const before = fixture(composerBefore, userBefore, collapsed, expanded, expected);
  assert.equal(before.result.confirmed, false);
  assert.equal(before.clicks, 0, 'UI ellipsis/control breaks the old exact-prefix test');
  const after = fixture(composerAfter, userAfter, collapsed, expanded, expected);
  assert.equal(after.clicks, 1);
  assert.equal(after.result.confirmed, true, 'full text required after expansion');
  assert.equal(after.final, expected);
  assert.equal(sha(after.final), sha(expected));
  assert.ok(expected.startsWith(after.initial));
  const wrongPrefix = fixture(composerAfter, userAfter, collapsed, expanded, 'Unrelated ' + expected);
  assert.equal(wrongPrefix.clicks, 0);
  assert.equal(wrongPrefix.result.confirmed, false);
  const wrongTail = fixture(composerAfter, userAfter, collapsed, expanded, expected + ' EXTRA UNSENT TAIL');
  assert.equal(wrongTail.clicks, 1);
  assert.equal(wrongTail.result.confirmed, false, 'a prefix never confirms Send');
  for (const options of [{ baseline: true }, { role: 'assistant' }]) {
    const unrelated = fixture(composerAfter, userAfter, collapsed, expanded, expected, options);
    assert.equal(unrelated.clicks, 0);
    assert.equal(unrelated.result.confirmed, false);
  }
  return { beforeLength: before.initial.length, prefixLength: after.initial.length, afterLength: after.final.length, exactSha256: sha(expected) };
}
const synthetic = check({ html: bubble(prefix, false), text: prefix + '\n\n…\nShow more' }, { html: bubble(raw, true), text: raw + '\n\nShow less' }, raw);
// The prior literal-payload path remains exact when no rich payload is present.
const literalHtml = '<div data-user-message-bubble="true"><div class="whitespace-pre-wrap" dir="auto">Legacy literal … Show less.</div><button data-markdown-copy="exclude">Show less</button></div>';
for (const [composer, user] of [[composerBefore, userBefore], [composerAfter, userAfter]]) {
  const legacy = fixture(composer, user, { html: literalHtml }, { html: literalHtml }, 'Legacy literal … Show less.');
  assert.equal(legacy.result.confirmed, true);
  assert.equal(legacy.final, 'Legacy literal … Show less.');
}
let captured = null;
if (captureDir) {
  const read = (name) => JSON.parse(fs.readFileSync(path.join(captureDir, name), 'utf8'));
  const collapsed = read('leaf1_round3_collapsed_user.json');
  const expanded = read('leaf1_round3_expanded_user.json');
  const checkpoint = read('leaf1_round3_uncertainty_checkpoint.json').turn;
  const input = checkpoint.input.message || checkpoint.input.input[0].text;
  const observedRich = read('leaf1_round3_rich_payload.json');
  assert.equal(observedRich.text, input, 'actual expanded native rich payload equals original immutable submitted input');
  assert.equal(render(parseCapturedHtml(expanded.html).querySelector(richSelector)), input);
  captured = check(collapsed, expanded, input);
  assert.equal(captured.beforeLength, 9931);
  assert.equal(captured.prefixLength, 9918);
  assert.equal(captured.afterLength, 19178);
}
console.log(JSON.stringify({ status: 'OFFLINE_PASS', synthetic, captured, live: 'NOT_RUN', submissionGuard: 'Full submitted text/hash still required; wrong prefix, wrong tail, existing turn and wrong role refused.' }));
