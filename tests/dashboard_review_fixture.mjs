// OFFLINE ONLY: production dashboard JS + a minimal synthetic DOM + local test HTTP.
// The supplied server must be pytest's disposable scripted-transport project.
import assert from 'node:assert/strict';
import vm from 'node:vm';

const [base, mode = 'exercise', originalId = '', expectedPending = ''] = process.argv.slice(2);
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
const html = await (await fetch(base + '/')).text();
const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, {
  id, style: {}, hidden: false, disabled: false, open: false, value: '', textContent: '',
  innerHTML: '', scrollTop: 0, scrollHeight: 0, contains: () => false,
  querySelectorAll: () => [], addEventListener() {}, setAttribute() {},
  showModal() { this.open = true; }, close() { this.open = false; },
}]));
let hold = null;
const context = vm.createContext({
  document: { hidden: false, activeElement: null, getElementById: id => elements.get(id),
    querySelectorAll: () => [], addEventListener() {} },
  window: {}, navigator: {}, setInterval() {}, setTimeout() {},
  fetch: async (path, options) => {
    if (hold && path === '/api/decision') await hold.promise;
    return fetch(base + path, options);
  },
});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const run = source => vm.runInContext(source, context);
const element = id => elements.get(id);
async function until(predicate) {
  for (let i = 0; i < 200; i++) {
    await run('refresh()');
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw Error('Dashboard state did not reach expected isolated test checkpoint');
}
const post = async (path, body) => {
  const response = await fetch(base + path, { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  assert.equal(response.status, 200);
  return response.json();
};
await until(() => run('Boolean(current)'));
if (mode === 'inspect') {
  assert.equal(run('current.id'), expectedPending);
  assert.notEqual(run('current.id'), originalId);
  assert.equal(run(`state.review_history.find(a=>a.id===${JSON.stringify(originalId)}).approval_source`), 'HUMAN_APPROVED');
  assert.ok(element('reviewIdentity').textContent.includes(expectedPending));
  console.log(JSON.stringify({ mode, restoredPending: expectedPending, oldApprovedNotReopened: true }));
  process.exit(0);
}

const initial = JSON.parse(run('JSON.stringify(current)'));
const staleSnapshot = run('JSON.stringify(state)');
hold = {};
hold.promise = new Promise(resolve => { hold.release = resolve; });
const inFlight = run("decision('approve')"); // Explicit synthetic approval of this temp fixture only.
assert.equal(element('approve').disabled, true);
hold.release();
await inFlight;
hold = null;
assert.equal(element('approve').disabled, false);
assert.equal(element('reviewDialog').open, false);
assert.ok(element('actionStatus').textContent.includes(initial.content_hash));
assert.ok(element('actionStatus').textContent.includes('等待调度'));
run(`state=${staleSnapshot};render()`); // Delayed pre-click polling cannot reopen an acknowledged item.
assert.equal(element('reviewDialog').open, false);
await run('refresh()');
assert.equal(run('state.approvals.length'), 0);
assert.equal(run('state.review_history[0].execution_status'), 'WAITING_FOR_DISPATCH');
const duplicate = await post('/api/decision', {
  approval_id: initial.id, content_hash: initial.content_hash, decision: 'approve',
});
assert.equal(duplicate.duplicate, true);
assert.equal(duplicate.approval.approval_source, 'HUMAN_APPROVED');
await post('/api/review-mode', { enabled: false });
await post('/api/review-mode', { enabled: true });
await run('refresh()');
assert.equal(run('state.approvals.length'), 0); // Human approval cannot be rearmed.
await post('/api/project', { status: 'ACTIVE' });

const reviewed = [initial.id];
for (let i = 0; i < 3; i++) { // report 1, prompt 2, report 2; next item is prompt 3.
  await until(() => run('Boolean(current)'));
  const item = JSON.parse(run('JSON.stringify(current)'));
  assert.ok(!reviewed.includes(item.id));
  assert.ok(element('reviewIdentity').textContent.includes(item.id));
  assert.ok(element('reviewIdentity').textContent.includes(item.content_hash));
  assert.ok(element('reviewPriorNotice').textContent.includes('另一项'));
  reviewed.push(item.id);
  await run("decision('approve')"); // Explicit synthetic test action, never an existing project.
  assert.equal(element('reviewDialog').open, false);
}
await until(() => run('Boolean(current)'));
const next = JSON.parse(run('JSON.stringify(current)'));
assert.ok(next.round_id.endsWith('r000003'));
assert.ok(!reviewed.includes(next.id));
run('current={...current,content_hash:"stale-content-hash"}');
await run("decision('approve')");
assert.equal(element('reviewDialog').open, true);
assert.match(element('reviewError').textContent, /HTTP 400.*Content changed/);
assert.equal(element('approve').disabled, false);
await run('refresh()');
console.log(JSON.stringify({ mode, originalId: initial.id, distinctApproved: reviewed,
  nextPending: next.id, staleErrorVisible: true, stalePollDidNotReopen: true,
  inFlightDisabled: true, waitingForDispatchVisible: true }));
