// Real reducer/router/materializer/TurnManager propagation; no browser or HTTP.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { pathToFileURL } from 'node:url';
const upstream = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const module = async (name) => import(pathToFileURL(path.join(upstream, name)).href);
const { RequestEventType: E, createRequestEvent } = await module('src/bridge/state/requestEvents.js');
const { reduceRequestState } = await module('src/bridge/state/requestMachine.js');
const { BridgeClientEventRouter } = await module('src/bridge/coordinator/bridgeClientEventRouter.js');
const { RequestResultMaterializer } = await module('src/bridge/coordinator/requestResultMaterializer.js');
const { TurnManager } = await module('src/turnManager.js');
const { MetadataStore } = await module('src/metadataStore.js');
let sequence = 0;
const event = (type, data = {}) => createRequestEvent(type, 'own-request', data,
  { eventId: 'fixture-' + ++sequence, occurredAt: sequence, receivedAt: sequence });
function prepared() {
  let state = reduceRequestState(null, event(E.CREATED, { sourceClientId: 'own-client', sessionId: 'own-conversation' })).state;
  state = reduceRequestState(state, event(E.PROMPT_ACCEPTED)).state;
  return reduceRequestState(state, event(E.EFFECT_STARTED, { effectId: 'own-effect', effectType: 'prompt.submit' })).state;
}
const proof = { effectId: 'own-effect', effectType: 'prompt.submit', code: 'COMPOSER_TEXT_VERIFY_FAILED',
  provenNotExecuted: true, cancellationEvidence: { source: 'composer_preparation', reason: 'submission_boundary_not_entered' },
  message: 'Composer preparation stopped before Send' };
let canonical = prepared();
const runtime = { requestId: 'own-request', clientId: 'own-client', events: [], followers: new Set() };
const pending = new Map([['own-request', runtime]]);
const router = new BridgeClientEventRouter({ pending, commands: new Map(), artifacts: new Map(),
  lifecycle: {
    getState: () => canonical, touchState() {}, markPromptAccepted() {},
    canonicalEvent: (_runtime, type, data) => event(type, data),
    ingestRequestTransition(_runtime, next) { const outcome = reduceRequestState(canonical, next); canonical = outcome.state; return outcome; },
    emitRequestEvent(_runtime, next) { runtime.events.push(next); },
  },
});
router.handleClientMessage('other-client', { type: 'request.effect.cancelled', requestId: 'own-request', ...proof });
assert.equal(canonical.terminal, null, 'another client cannot prove this request not sent');
router.handleClientMessage('own-client', { type: 'request.effect.cancelled', requestId: 'own-request', ...proof });
assert.equal(canonical.lifecycle, 'failed');
assert.equal(canonical.terminal.evidence.provenNotExecuted, true);
assert.equal(canonical.submission, 'accepted');
assert.equal(canonical.response.userTurnKey, '');
assert.equal(runtime.events.at(-1).provenNotExecuted, true, 'public effect evidence preserves the proof');
const duplicate = reduceRequestState(canonical, event(E.EFFECT_CANCELLED, proof));
assert.equal(duplicate.accepted, false, 'terminal records cannot be rewritten by duplicate settlement');

for (const [state, fields] of [
  [prepared(), { ...proof, provenNotExecuted: false }],
  [prepared(), { ...proof, cancellationEvidence: { source: 'guess', reason: 'no_confirmation' } }],
  [{ ...prepared(), submission: 'submitted', response: { ...prepared().response, userTurnKey: 'submitted-user' } }, proof],
  [{ ...prepared(), generation: 'active' }, proof],
]) {
  const result = reduceRequestState(state, event(E.EFFECT_CANCELLED, fields));
  assert.equal(result.state.terminal, null, 'absence/conflicting evidence never becomes NOT_SENT');
  assert.equal(result.effects.length, 0);
}
const uncertain = reduceRequestState(prepared(), event(E.EFFECT_UNCERTAIN,
  { effectId: 'own-effect', effectType: 'prompt.submit', message: 'Missing proof after click' }));
assert.equal(uncertain.state.terminal, null);
assert.ok(uncertain.effects.every((effect) => effect.type !== 'prompt.execution.step'));
const oldNotStarted = reduceRequestState(uncertain.state, event(E.EFFECT_RECONCILED,
  { effectType: 'prompt.submit', outcome: 'not_started', retryPolicy: 'if_unconfirmed' }));
assert.equal(oldNotStarted.state.terminal.code, 'recovery_uncertain');
assert.equal(oldNotStarted.state.terminal.evidence.safeToRetryAsNewRequest, false);
assert.ok(oldNotStarted.effects.every((effect) => effect.type !== 'prompt.execution.step'));

// A retained composer after a Send attempt is observation, not non-execution.
const context = vm.createContext({ console }); context.globalThis = context;
vm.runInContext(await fs.readFile(path.join(upstream, 'tools/chrome-bridge-extension/content/requestEffectReconciliation.js'), 'utf8'), context);
let settlement;
const reconcile = context.ChatGptRequestEffectReconciliation.createRequestEffectReconciliation({
  getActiveRequest: () => ({ requestId: 'own-request', phase: 'prompt_accepted_by_content_script', options: {},
    responseEpoch: 0, pendingSubmittedTurnExpectedText: 'exact prompt', pendingSubmittedTurnBaseline: new Set(['old-user']) }),
  findComposer: () => ({ value: 'exact prompt' }), getCurrentSession: () => ({ id: 'own-conversation' }),
  settleEffectReconciliation: async (result) => { settlement = result; }, diagnostic() {},
});
await reconcile.handleEffectReconcile({ requestId: 'own-request', commandId: 'own-command', effectId: 'own-effect', effectType: 'prompt.submit' });
assert.equal(settlement.reconciliationOutcome, 'uncertain');

let bridgeError;
runtime.reject = (error) => { bridgeError = error; };
const owner = { pending, runtime: new Map(), emitRequestEvent: (_state, next) => runtime.events.push(next) };
await new RequestResultMaterializer(owner).finishFromCanonicalState(runtime, canonical);
assert.equal(bridgeError.code, 'COMPOSER_TEXT_VERIFY_FAILED');
assert.equal(bridgeError.provenNotExecuted, true);
assert.equal(runtime.events.at(-1).provenNotExecuted, true);

const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'bridge-delivery-fixture-'));
const store = new MetadataStore(directory);
try {
  await store.ready;
  let executions = 0;
  const manager = new TurnManager({ metadataStore: store,
    bridge: { async sendRequest() { executions++; throw bridgeError; } }, resultResolver: {} });
  const first = await manager.startTurn({ id: 'local-own-turn', message: 'exact approved prompt', sourceClientId: 'own-client' },
    { idempotencyKey: 'closed-own-identity' });
  let terminal;
  for (let i = 0; i < 100; i++) {
    terminal = await manager.getTurn(first.turn.id);
    if (terminal.status === 'failed' && !manager.isTurnTracked(first.turn.id)) break;
    await new Promise(setImmediate);
  }
  assert.equal(terminal.status, 'failed');
  assert.equal(terminal.output, null);
  assert.equal(terminal.error.code, 'COMPOSER_TEXT_VERIFY_FAILED');
  assert.equal(terminal.error.provenNotExecuted, true);
  assert.equal(terminal.error.recoverable, false);
  assert.deepEqual(terminal.error.cancellationEvidence, proof.cancellationEvidence);
  const reused = await manager.startTurn({ message: 'must not execute' }, { idempotencyKey: 'closed-own-identity' });
  assert.equal(reused.reused, true);
  assert.equal(executions, 1, 'a closed request identity never causes automatic inference replay');
} finally {
  await fs.rm(directory, { recursive: true, force: true });
}
console.log('PASS: exact pre-Send proof becomes durable failed + provenNotExecuted evidence; conflicting/uncertain state never retries; terminal identity reuse preserves the original failure.');
