// State-backed regression: a reconciliation read must finish its own command.
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const moduleAt = (file) => import(pathToFileURL(path.join(root, file)));
const { BackgroundStateStore } = await moduleAt('tools/chrome-bridge-extension/background/stateV6.js');
const { handleEffectReconciliationSettlement, handleReleaseCleanupSettlement } = await moduleAt('tools/chrome-bridge-extension/background/portRouter.js');
const values = new Map();
const storage = {
  async get(key) { return { [key]: structuredClone(values.get(key)) }; },
  async set(entries) { for (const [key, value] of Object.entries(entries)) values.set(key, structuredClone(value)); },
};
const store = new BackgroundStateStore(storage, 'background-check');
const state = { tabId: 991, contentEpoch: 'content-check' };
const lease = { requestId: 'request-check', leaseId: 'lease-check', ownerServerInstanceId: 'owner-check', responseEpoch: 0 };
let sequence = 0;
let flushed = 0;
const envelope = (type, body = {}) => ({ protocolVersion: 5, messageId: `check-${++sequence}`, messageType: type, body });
const deps = { backgroundState: store,
  createEnvelopeDraft: (_state, type, body) => envelope(type, body),
  flushCriticalOutbox: async () => { flushed += 1; } };
async function transition(event) {
  const result = await store.transition(state.tabId, { ...event, contentEpoch: state.contentEpoch });
  assert.equal(result.accepted, true, result.reason);
  return result.state;
}
await transition({ type: 'content.attached' });
await transition({ type: 'lease.claim', ...lease });
await transition({ type: 'lease.executing', ...lease });
async function command(commandId, commandType, mode, terminalEnvelope = null) {
  await transition({ type: 'command.registered', ...lease, commandId, commandType, mode, scope: 'request', terminalEnvelope });
  await transition({ type: 'command.dispatched', ...lease, commandId, acceptedEnvelope: envelope('command.accepted') });
}
await command('reconcile-check', 'request.effect.reconcile', 'result');
await transition({ type: 'effect_command.dispatched', ...lease,
  commandId: 'real-work', commandType: 'prompt.send', effectId: 'real-work-effect', kind: 'page.ready.initial',
  idempotencyKey: 'real-work-key', preconditionsHash: 'real-work-hash', acceptedEnvelope: envelope('command.accepted') });
await command('release-check', 'request.release', 'release', envelope('lease.released', { requestId: lease.requestId }));
await transition({ type: 'lease.releasing', ...lease });
await handleReleaseCleanupSettlement(deps, state, { commandId: 'release-check', status: 'completed' });
let runtime = await store.read(state.tabId);
assert.ok(runtime.lease, 'Unfinished request children must retain the lease');
assert.ok(runtime.commands['release-check'].releaseReadyAt);
const settlement = { commandId: 'reconcile-check', effectId: 'prompt.submit:unconfirmed', effectType: 'prompt.submit',
  reconciliationOutcome: 'uncertain', reconciliationReason: 'submission_not_provable', evidence: {} };
await assert.rejects(handleEffectReconciliationSettlement(deps, state, { ...settlement, commandId: 'real-work' }), /persisted result command/);
await handleEffectReconciliationSettlement(deps, state, settlement);
runtime = await store.read(state.tabId);
assert.equal(runtime.commands['reconcile-check'].status, 'succeeded');
assert.ok(runtime.outbox.some((item) => item.messageType === 'command.result' && item.body.reconciliationOutcome === 'uncertain'));
assert.ok(runtime.lease, 'Another genuinely active physical effect must still block release');
await transition({ type: 'effect.succeeded', ...lease, effectId: 'real-work-effect', idempotencyKey: 'real-work-key',
  preconditionsHash: 'real-work-hash', terminalEnvelope: envelope('effect.succeeded') });
runtime = await store.read(state.tabId);
assert.equal(runtime.lease, null);
assert.equal(runtime.commands['release-check'].status, 'succeeded');
assert.equal(runtime.outbox.filter((item) => item.messageType === 'lease.released').length, 1);
assert.ok(flushed >= 2);
console.log('PASS: exact reconciliation result command settled; real active work retained barrier; lease released only after every child finished.');
