// Request/user-anchor guards remain mandatory for temporary-ID promotion.
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const { tabObservationToCanonicalEvent: adapt } = await import(pathToFileURL(path.join(root, 'src/bridge/adapters/tabObservationAdapter.js')));
const temporary = 'local-chatgpt:4b62870c-08e1-46d1-b1bc-5fbb7a01a987';
const persistent = '6acf3c3b-1af0-83ea-a62d-c2b0f333505e';
function check(before, after, { request = 'req-1', user = 'user-1' } = {}) {
  return adapt('req-1', 'client-1', { observation: {
    revision: 1, observedAt: 100, conversationId: after,
    url: `https://chatgpt.com/c/${after}`,
    generation: { state: 'active' }, blocker: { state: 'none' },
    output: { state: 'reasoning', answer: '' }, artifact: { state: 'none', count: 0 },
    error: { explicit: false }, turn: { key: 'assistant-1', userKey: user, index: 1 },
    activeRequest: { requestId: request, submittedUserTurnKey: 'user-1', responseEpoch: 0 },
  } }, { submission: 'submitted', source: { conversationId: before },
    response: { epoch: 0, userTurnKey: 'user-1' } }, 110).data;
}
for (const before of [temporary, temporary.replace(':', '%3A'), 'WEB:4b62870c-08e1-46d1-b1bc-5fbb7a01a987']) {
  assert.equal(check(before, persistent).conversationCanonicalized, true);
  assert.equal(check(before, persistent).conversationChanged, false);
  assert.equal(check(before, persistent, { user: 'other-user' }).conversationChanged, true);
  assert.equal(check(before, persistent, { request: 'other-request' }).conversationChanged, true);
}
assert.equal(check(temporary, temporary.replace(':', '%3A')).conversationChanged, false);
for (const before of ['local-chatgpt:not-a-uuid', 'local-chatgpt%3Xbad', temporary.replace(':', '%253A'), 'existing-persistent-id']) {
  assert.equal(check(before, persistent).conversationCanonicalized, false);
  assert.equal(check(before, persistent).conversationChanged, true);
}
assert.equal(check(temporary, 'local-chatgpt:ffffffff-ffff-ffff-ffff-ffffffffffff').conversationChanged, true);
console.log('PASS: encoded/plain temporary promotion with exact request/user anchors; mismatches, malformed IDs and real conversation changes rejected.');
