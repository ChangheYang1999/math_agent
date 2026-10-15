// Offline regression of real background forwarding and abortable picker waits.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';

const root = path.resolve(process.argv[2]);
process.chdir(root);
const url = (name) => pathToFileURL(path.join(root, name));
const { handleServerEnvelope: afterRoute } = await import(url('tools/chrome-bridge-extension/background/serverEnvelopeRouter.js'));
const { BackgroundStateStore } = await import(url('tools/chrome-bridge-extension/background/stateV6.js'));
const { createProtocolOutbox } = await import(url('tools/chrome-bridge-extension/background/outboxV5.js'));
const { createExtensionEnvelope, ExtensionMessageType } = await import(url('src/bridge/protocol/v5.js'));
const { MessageType } = await import(url('tools/chrome-bridge-extension/background/protocolV5.js'));
const { parseCapturedHtml } = await import(url('test/helpers/offlineChatDom.js'));
const relative = 'tools/chrome-bridge-extension/content/intelligenceCommands.js';
const after = fs.readFileSync(path.join(root, relative), 'utf8');
const before = fs.existsSync(path.join(root, relative + '.pre-picker-activation'))
  ? fs.readFileSync(path.join(root, relative + '.pre-picker-activation'), 'utf8')
  : execFileSync('git', ['show', `HEAD:${relative}`], { cwd: root, encoding: 'utf8' });
const oldRouteSource = execFileSync('git', ['show', 'HEAD:tools/chrome-bridge-extension/background/serverEnvelopeRouter.js'], { cwd: root, encoding: 'utf8' });
const activations = [];
const chrome = { tabs: { async update(tabId, options) { activations.push({ tabId, options }); } } };
globalThis.chrome = chrome;
globalThis.WebSocket = { OPEN: 1 };
const routeContext = vm.createContext({ chrome, MessageType, console, ChatGptBridgeCommandManifest: globalThis.ChatGptBridgeCommandManifest });
vm.runInContext(oldRouteSource.replace(/^import .*;\n/gm, '').replace('export async function handleServerEnvelope', 'async function handleServerEnvelope'), routeContext);

async function route(handler, tabId, commandType) {
  const values = new Map();
  const storage = { async get(key) { return { [key]: structuredClone(values.get(key)) }; }, async set(items) { for (const [key, value] of Object.entries(items)) values.set(key, structuredClone(value)); } };
  const backgroundState = new BackgroundStateStore(storage, 'offline-background');
  const state = { tabId, clientId: `own-${tabId}`, contentEpoch: 'offline-content', connectionEpoch: 'offline-connection', port: {}, ws: { readyState: 1, send() {} } };
  await backgroundState.transition(tabId, { type: 'content.attached', contentEpoch: state.contentEpoch });
  const posted = [];
  const post = (_port, message) => posted.push({ message, activationCount: activations.length });
  const outbox = createProtocolOutbox({ backgroundEpoch: 'offline-background', backgroundState, post, summarize: (value) => value });
  const envelope = createExtensionEnvelope(ExtensionMessageType.COMMAND_EXECUTE, { type: commandType, commandId: 'offline-command', targetCommandId: 'prior' }, { messageId: 'offline-message', commandId: 'offline-command', source: { clientId: 'server', tabId: 999999, backgroundEpoch: 'offline-server', contentEpoch: '', sequence: 1 } });
  await handler({ state, envelope, backgroundState, ...outbox, post, scheduleReleaseDeadline() {} });
  return posted.filter((entry) => entry.message.type === 'server.message');
}
const oldPosts = await route(routeContext.handleServerEnvelope, 8894, 'models.list');
assert.equal(oldPosts.length, 1);
assert.equal(activations.length, 0, 'before patch, background discovery does not activate its hidden tab');
for (const [tabId, type] of [[8894, 'models.list'], [8897, 'efforts.list']]) {
  const count = activations.length;
  const posts = await route(afterRoute, tabId, type);
  assert.equal(posts.length, 1);
  assert.deepEqual(activations[count], { tabId, options: { active: true } });
  assert.equal(posts[0].activationCount, count + 1, 'await activation before content forwarding');
  assert.equal(posts[0].message.payload.type, type);
}
const count = activations.length;
for (const type of ['response.recover.latest', 'command.cancel']) await route(afterRoute, 8894, type);
assert.equal(activations.length, count, 'unrelated commands must not activate a tab');
assert.equal(Object.keys(chrome.tabs).join(','), 'update', 'fixture exposes no create/reload/navigation or Send');

const flush = async () => { for (let i = 0; i < 15; i += 1) await Promise.resolve(); };
async function cancelledRead(source, withCandidate, handler) {
  let now = 1;
  let nextId = 0;
  let clicks = 0;
  let uiActions = 0;
  const timers = new Map();
  const setTimer = (fn, ms) => { const id = ++nextId; timers.set(id, { fn, at: now + ms }); return id; };
  const clearTimer = (id) => timers.delete(id);
  const rootNode = parseCapturedHtml('<main><form><textarea></textarea><button aria-haspopup="menu" aria-expanded="false" aria-label="Select ChatGPT model">GPT-6 Thinking</button></form></main>');
  const button = rootNode.querySelector('button');
  button.click = () => { clicks += 1; uiActions += 1; };
  button.focus = () => { uiActions += 1; };
  button.scrollIntoView = () => { uiActions += 1; };
  rootNode.body = rootNode;
  rootNode.activeElement = null;
  rootNode.dispatchEvent = () => { uiActions += 1; };
  const context = vm.createContext({ document: rootNode, console, Date: { now: () => now }, setTimeout: setTimer, clearTimeout: clearTimer, KeyboardEvent: class {}, window: {}, MouseEvent: class {} });
  vm.runInContext(source, context);
  const sent = [];
  const api = context.ChatGptIntelligenceCommands.createIntelligenceCommands({
    DOM_PARSER: { canonicalEffortId: () => '' },
    delay: (ms) => new Promise((resolve) => setTimer(resolve, ms)), diagnostic() {},
    findComposer: () => withCandidate ? rootNode.querySelector('textarea') : null,
    findComposerRootStrict: () => withCandidate ? rootNode.querySelector('form') : null,
    isPrimaryChatSurfaceElement: () => true, isUsableButton: () => true, isVisible: () => true,
    normalizeComparable: (v) => String(v).toLowerCase(), normalizeText: (v) => String(v || '').trim(),
    unique: (v) => [...new Set(v)], visibleText: (node) => node.textContent || '',
    buttonSignalText: (node) => `${node.getAttribute('aria-label')} ${node.textContent}`,
    send: (message) => sent.push(message),
  });
  const controller = new AbortController();
  let settled = false;
  const pending = api[handler]({ commandId: 'offline-discovery', signal: controller.signal }).then(() => { settled = true; });
  await flush();
  if (withCandidate) {
    for (const [id, timer] of [...timers]) { timers.delete(id); now = timer.at; timer.fn(); }
    await flush();
    assert.equal(clicks, 1, 'reach picker-open wait after exactly one activation');
  }
  assert.equal(timers.size, 1);
  const actionsAtAbort = uiActions;
  controller.abort(new Error('offline cancellation'));
  await flush();
  return { settled, timers: timers.size, clicks, postAbortUiActions: uiActions - actionsAtAbort, error: sent.at(-1)?.type, pending };
}
for (const handler of ['handleModelsList', 'handleEffortsList']) for (const candidate of [false, true]) {
  const broken = await cancelledRead(before, candidate, handler);
  assert.equal(broken.settled, false, 'before patch ignores AbortSignal and leaves picker work pending');
  assert.equal(broken.timers, 1);
  const fixed = await cancelledRead(after, candidate, handler);
  assert.equal(fixed.settled, true);
  assert.equal(fixed.timers, 0);
  assert.equal(fixed.postAbortUiActions, 0, 'no stale click, Escape or focus after cancellation');
  assert.equal(fixed.error, 'command.error');
}
console.log('OFFLINE_PASS: model/effort discovery activates only its connected existing tab before forwarding; other commands unchanged; cancellation clears real picker waits immediately without stale UI work. No browser or inference.');
