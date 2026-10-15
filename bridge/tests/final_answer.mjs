// Offline current-DOM regression; no browser, Send, history fetch, or inference.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';

const root = path.resolve(process.argv[2]);
process.chdir(root);
const relative = 'tools/chrome-bridge-extension/content/currentTurnDom.js';
const before = execFileSync('git', ['show', `HEAD:${relative}`], { cwd: root, encoding: 'utf8' });
const after = fs.readFileSync(path.join(root, relative), 'utf8');
const { createAssistantFixtureParser, parseCapturedHtml } = await import(pathToFileURL(path.join(root, 'test/helpers/offlineChatDom.js')));
const answer = JSON.stringify({ status: 'PARTIAL', evidence: 'E(x) ≥ 4 sin²(π/N) M(x); N ≥ 3.' });
const user = '<div class="group/user-message" data-chatgpt-search-message-ids="own-user"><div data-content-search-unit-key="own:0:user">The exact user prompt</div></div>';
const recap = '<div class="block-BQZwFn"><span hidden data-chatgpt-agent-turn-start></span><div class="group/activity-header"><button aria-expanded="false"></button><span>Worked for 5m 59s</span></div></div>';
const final = `<div data-content-search-unit-key="own:2:assistant" data-chatgpt-search-message-ids="own-final"><div class="MarkdownRoot-test"><p>${answer}</p></div></div>`;
const keyed = (contents, key = 'own-user') => `<div data-turn-key="${key}"><div class="flex flex-col">${contents}</div></div>`;
const html = `<main>${keyed(user + recap + final)}</main>`;

function turns(source, input) {
  const context = vm.createContext({ Node: { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 } });
  vm.runInContext(source, context);
  const dom = context.ChatGptCurrentTurnDom.createCurrentTurnDom();
  const rootNode = parseCapturedHtml(input);
  return { dom, nodes: Array.from(dom.getTurnNodes(rootNode)), rootNode };
}
const broken = turns(before, html);
assert.equal(broken.nodes.find((node) => broken.dom.turnRole(node) === 'assistant').textContent, 'Worked for 5m 59s', 'reproduce observed Pro recap misclassification');
const fixed = turns(after, html);
const assistant = fixed.nodes.find((node) => fixed.dom.turnRole(node) === 'assistant');
assert.equal(assistant.textContent, answer);
assert.equal(fixed.dom.currentTurnIdentity(assistant), 'own-user');
assert.equal(fixed.dom.isCurrentAssistantNode(assistant), true);
assert.equal(fixed.dom.getFinalAssistantNode(assistant, (node) => fixed.dom.isCurrentAssistantNode(node)), assistant);
assert.equal(fixed.dom.selectAssistantForSubmittedUser(fixed.nodes.map((turn) => ({ turn, role: fixed.dom.turnRole(turn), key: fixed.dom.currentTurnKey(turn) })), 'own-user::user', () => null)?.turn, assistant);

const placeholder = turns(after, `<main>${keyed(user + recap)}${keyed(final, 'unrelated')}</main>`);
assert.equal(placeholder.nodes.filter((node) => placeholder.dom.turnRole(node) === 'assistant').length, 0, 'recap alone must not become a final reply or steal another keyed turn');
const interval = turns(after, `<main>${keyed(user + recap + recap + final)}</main>`);
assert.equal(interval.nodes.filter((node) => interval.dom.turnRole(node) === 'assistant').length, 1, 'a final message belongs only to its immediately preceding marker');
const old = '<main><section data-turn="user" data-turn-id="legacy-user">Prompt</section><section data-turn="assistant" data-turn-id="legacy-answer"><div data-message-author-role="assistant" data-message-id="legacy-answer"><p>Legacy answer</p></div></section></main>';
for (const source of [before, after]) assert.equal(turns(source, old).nodes.length, 2);
const oldKeyed = `<main>${keyed(user + '<div><span hidden data-chatgpt-agent-turn-start></span><p>Previous keyed answer</p></div>')}</main>`;
for (const source of [before, after]) {
  const result = turns(source, oldKeyed);
  assert.equal(result.nodes.find((node) => result.dom.turnRole(node) === 'assistant').textContent, 'Previous keyed answer');
}

const parser = await createAssistantFixtureParser();
parser.mount(html);
const snapshot = parser.snapshots.readLatestAssistantSnapshot();
assert.equal(snapshot.answer, answer, 'full production parser preserves the complete JSON and math');
assert.equal(snapshot.hasFinalMessage, true);
parser.mount(`<main>${keyed(user + recap)}</main>`);
assert.equal(parser.snapshots.readLatestAssistantSnapshot().answer, '');

let captured = null;
if (process.argv[3]) {
  const capture = JSON.parse(fs.readFileSync(path.resolve(process.argv[3]), 'utf8'))[0];
  const original = turns(before, `<main>${capture.html}</main>`);
  const patched = turns(after, `<main>${capture.html}</main>`);
  const oldAnswer = original.nodes.find((node) => original.dom.turnRole(node) === 'assistant');
  const newAnswer = patched.nodes.find((node) => patched.dom.turnRole(node) === 'assistant');
  assert.equal(oldAnswer.textContent.trim(), 'Worked for 5m 59s');
  assert.equal(newAnswer.getAttribute('data-content-search-unit-key'), 'fallback-turn-0:2:assistant');
  const expected = patched.rootNode.querySelector('[data-content-search-unit-key="fallback-turn-0:2:assistant"]');
  assert.equal(newAnswer, expected, 'select the exact captured final DOM without altering its JSON/math');
  assert.equal(patched.dom.currentTurnIdentity(newAnswer), capture.key);
  captured = { beforeLength: oldAnswer.textContent.length, afterLength: newAnswer.textContent.length, exactFinalNode: true };
}
console.log(JSON.stringify({ status: 'OFFLINE_PASS', before: 'reproduced 17-character reasoning recap', after: 'exact final assistant content; placeholder fails closed; user/key/marker interval and legacy cases preserved', captured, live: 'NOT_RUN' }));
