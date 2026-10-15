// Offline regression: actual keyed DOM helpers and request.resume, never a browser.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';

const root = process.argv[2] || path.join(os.homedir(), '.local/share/math-research-agent/chatgpt-bridge');
process.chdir(root);
const relative = 'tools/chrome-bridge-extension/content/requestResumeCommands.js';
const before = execFileSync('git', ['show', `HEAD:${relative}`], { cwd: root, encoding: 'utf8' });
const after = fs.readFileSync(path.join(root, relative), 'utf8');
const currentDom = fs.readFileSync(path.join(root, 'tools/chrome-bridge-extension/content/currentTurnDom.js'), 'utf8');
const { createAssistantFixtureParser } = await import(pathToFileURL(path.join(root, 'test/helpers/offlineChatDom.js')));
const normalizeText = (value) => String(value || '').trim().replace(/\s+/g, ' ');
const currentHtml = `<main><div data-turn-key="current-own">
  <div class="user-branch"><div class="group/user-message" data-chatgpt-search-message-ids="own-user">
    <div data-content-search-unit-key="own-user"><p>Exact submitted prompt</p></div>
  </div></div>
  <div class="assistant-branch"><span hidden data-chatgpt-agent-turn-start></span>
    <div data-content-search-unit-key="own-assistant" data-chatgpt-search-message-ids="assistant-record">
      <div class="MarkdownRoot-test"><p>Existing answer</p></div>
    </div>
  </div>
</div></main>`;
const legacyHtml = `<main>
  <section data-turn="user" data-turn-id="legacy-user"><p>Exact submitted prompt</p></section>
  <section data-turn="assistant" data-turn-id="legacy-assistant"><p>Existing answer</p></section>
</main>`;

async function resume(source, html, projection) {
  const parser = await createAssistantFixtureParser();
  parser.mount(html);
  const roles = Array.from(parser.snapshots.getTurnNodes(), parser.snapshots.turnRole);
  const context = vm.createContext({
    console, location: { href: 'https://chatgpt.com/c/offline-resume-role-fixture' },
    document: { title: 'Offline fixture' },
    Node: { TEXT_NODE: 3, DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 },
  });
  vm.runInContext(currentDom, context);
  vm.runInContext(source, context);
  const sent = [];
  let observed = 0;
  let submitCalls = 0;
  const request = {
    requestId: 'offline-original-request',
    update(_type, patch) { Object.assign(this, patch); },
  };
  const commands = context.ChatGptRequestResumeCommands.createRequestResumeCommands({
    publicRequestStatus: () => ({ requestId: request.requestId }),
    getActiveRequest: () => request,
    getCurrentSession: () => ({ id: 'offline-session' }),
    getTurnNodes: parser.snapshots.getTurnNodes,
    turnKey: parser.snapshots.turnKey,
    normalizeText,
    waitForChatPageReady: async () => {},
    resumeBoundaryTimeoutMs: 0,
    send: (message) => sent.push(message),
    diagnostic: () => {},
    startDomMonitor: () => {},
    collectAndEmit: () => { observed += 1; },
    enterPrompt: () => { submitCalls += 1; throw new Error('Resume must never submit'); },
  });
  await commands.handleRequestResume({
    commandId: 'offline-resume', requestId: request.requestId,
    projection: { responseEpoch: 1, sentAt: 1234, ...projection },
  });
  assert.equal(observed, 1);
  assert.equal(submitCalls, 0, 'read-only recovery must never invoke Send');
  return { response: sent.at(-1), request, roles };
}

const projection = {
  submittedUserTurnKey: 'current-own::user', submittedPromptText: 'Exact submitted prompt',
  assistantTurnKey: 'current-own::assistant',
};
const broken = await resume(before, currentHtml, projection);
assert.deepEqual(broken.roles, ['user', 'assistant'], 'actual shared helper recognizes both current roles');
assert.equal(broken.response.boundaryStatus, 'missing', 'reproduce the legacy-only resume failure');
assert.equal(broken.response.boundaryEvidence.userTurnCount, 0);

const fixed = await resume(after, currentHtml, projection);
assert.equal(fixed.response.boundaryStatus, 'matched');
assert.equal(fixed.response.submittedUserTurnKey, projection.submittedUserTurnKey);
assert.equal(fixed.response.assistantTurnKey, projection.assistantTurnKey);
assert.equal(fixed.response.boundaryEvidence.exactKeyMatch, true);
assert.equal(fixed.response.boundaryEvidence.promptTextMatched, true);

const missing = await resume(after, currentHtml, {
  submittedUserTurnKey: 'unrelated::user', submittedPromptText: 'A different prompt',
});
assert.equal(missing.response.boundaryStatus, 'missing');
assert.equal(missing.response.assistantTurnKey, '');
assert.equal(missing.response.boundaryEvidence.userTurnCount, 1);

const rebound = await resume(after, currentHtml, {
  submittedUserTurnKey: 'old-own-key::user', submittedPromptText: 'Exact submitted prompt',
});
assert.equal(rebound.response.boundaryStatus, 'rebound');
assert.equal(rebound.response.submittedUserTurnKey, 'current-own::user');

for (const source of [before, after]) {
  const legacy = await resume(source, legacyHtml, {
    submittedUserTurnKey: 'legacy-user', submittedPromptText: 'Exact submitted prompt',
    assistantTurnKey: 'legacy-assistant',
  });
  assert.equal(legacy.response.boundaryStatus, 'matched');
  assert.equal(legacy.response.assistantTurnKey, 'legacy-assistant');
}
console.log('OFFLINE_PASS: current-DOM resume fails before and matches after; exact keys/text, missing-boundary refusal, legacy behavior and zero Send are preserved.');
