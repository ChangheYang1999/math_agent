// Recover observation of one already-sent request; this harness has no Send API.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const expected = 'RECOVERY-BEGIN\n' + 'The complete original literal payload.\n'.repeat(440) + 'RECOVERY-END';
const literal = { textContent: expected.slice(0, 10240) };
const bubble = { querySelectorAll: (selector) => selector === '.whitespace-pre-wrap[dir="auto"]' ? [literal] : [],
  textContent: expected + '\nShow less' };
const user = { role: 'user', key: 'own-new-user',
  matches: (selector) => selector.includes('data-chatgpt-search-message-ids'),
  getAttribute: () => null, querySelector: (selector) => selector === '[data-user-message-bubble="true"]' ? bubble : null };
const turns = [user];
const context = vm.createContext({ console, document: {}, Set, Date }); context.globalThis = context;
context.ChatGptTurnDom = { createTurnDom: () => ({ key: (turn) => turn.key, role: (turn) => turn.role,
  excluded: () => false, getTurnNodes: () => [], getFinalAssistantNode: () => null }) };
context.ChatGptCurrentTurnDom = { createCurrentTurnDom: () => ({
  getTurnNodes: () => turns, turnKey: (turn) => turn.key, turnRole: (turn) => turn.role,
  getFinalAssistantNode: () => null }) };
for (const file of ['requestState.js', 'userTurnState.js', 'turnUiSignals.js', 'turnSnapshots.js', 'requestMonitor.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'tools/chrome-bridge-extension/content', file), 'utf8'), context);
}
const normalizeText = (text) => String(text || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
const snapshots = context.ChatGptTurnSnapshots.createTurnSnapshots({
  DOM_PARSER: {}, collectArtifactsForAssistantNode: () => [],
  setRequestPhase: (request, phase) => { request.phase = phase; },
  normalizeText, visibleText: (node) => node?.textContent || '', isVisible: () => true,
  simpleHash: (text) => String(text.length), diagnostic() {}, emitChatEvent() {},
});
function recoveredRequest(baseline = ['old-user', 'old-assistant']) {
  // Supplying the old projection models in-memory reconnect only. Background
  // handshake does not persist this baseline across an actual document reload.
  const suppliedProjection = { requestId: 'original-already-sent', leaseId: 'same-lease', ownerServerInstanceId: 'same-server',
    sentAt: 0, turnCaptureArmed: true, submittedUserTurnKey: '',
    pendingSubmittedTurnBaseline: new Set(baseline), pendingSubmittedTurnKind: 'prompt',
    pendingSubmittedTurnExpectedText: expected, baselineTurnKeys: new Set(baseline) };
  const request = context.ChatGptRequestState.recoverRequestState(suppliedProjection,
    { lease: { requestId: suppliedProjection.requestId, leaseId: suppliedProjection.leaseId, ownerServerInstanceId: suppliedProjection.ownerServerInstanceId } });
  request.update = function (_type, patch) { Object.assign(this, patch); };
  return request;
}
let request = recoveredRequest();
let callback;
const reasons = [];
const monitor = context.ChatGptRequestMonitor.createRequestMonitor({
  getActiveRequest: () => request, refreshRequestTurnAnchors: snapshots.refreshRequestTurnAnchors,
  subscribeTabObservation: (fn) => { callback = fn; return {}; },
  scheduleTabObservation: (reason) => reasons.push(reason), diagnostic() {},
  findTurnByKey: () => null, findChatMain: () => ({ tagName: 'MAIN' }),
  send: () => { throw new Error('Observation recovery must never send anything'); },
});
monitor.startDomMonitor(request);
const observation = { activeRequest: { requestId: request.requestId }, turn: { userKey: user.key,
  userIndex: 2, key: 'own-existing-assistant', index: 3 } };
callback(observation);
assert.equal(request.submittedUserTurnKey, '', 'the collapsed prefix never proves full delivery');
literal.textContent = expected;
callback(observation);
assert.equal(request.requestId, 'original-already-sent');
assert.equal(request.submittedUserTurnKey, 'own-new-user');
assert.equal(request.assistantTurnKey, 'own-existing-assistant');
assert.equal(request.sentAt, 0, 'late observation must not invent a Send timestamp');
assert.equal(request.pendingSubmittedTurnExpectedText, '');
assert.ok(reasons.includes('request.user_turn_reconciled'));

request = recoveredRequest();
literal.textContent = expected.slice(0, -12) + 'WRONG-END';
callback(observation);
assert.equal(request.submittedUserTurnKey, '', 'a wrong tail cannot adopt the original inference');
literal.textContent = expected;
request = recoveredRequest(['own-new-user']);
callback(observation);
assert.equal(request.submittedUserTurnKey, '', 'the saved baseline prevents adopting an older turn');
request = recoveredRequest();
callback({ ...observation, activeRequest: { requestId: 'different-request' } });
assert.equal(request.submittedUserTurnKey, '', 'another active request observation cannot recover this one');
console.log('PASS: given the original in-memory projection, only its new complete literal user turn is adopted; existing assistant binds without Send/replay/new identity or invented timestamps. This does not prove projection persistence across document reload.');
