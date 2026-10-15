// Focused, browser-free check of the observed five-position picker patch.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const context = vm.createContext({ console, KeyboardEvent: class { constructor(type) { this.type = type; } } });
for (const file of ['artifactParserCore.js', 'domParserCore.js', 'content/intelligenceCommands.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'tools/chrome-bridge-extension', file), 'utf8'), context);
}
let statusText = 'Extra High, 4 of 5.';
let currentPosition = '3';
const toggle = { getAttribute: () => '', hasAttribute: () => false };
const control = {};
const slider = {
  getAttribute: (key) => ({ 'aria-valuemin': '0', 'aria-valuemax': '4', 'aria-valuenow': currentPosition })[key] ?? null,
  closest: () => control,
};
const panel = { hasAttribute: (key) => key === 'data-model-picker-power-slider', querySelector: () => slider };
const status = { get textContent() { return statusText; } };
let checkedModel = 0;
const radios = ['GPT-6', 'GPT-5.6 Sol', 'GPT-5.5'].map((label, index) => ({
  innerText: label, textContent: label, children: [],
  getAttribute: (name) => name === 'aria-checked' || name === 'data-model-selected'
    ? String(index === checkedModel) : '',
  querySelectorAll: () => [],
}));
const composer = {};
const trigger = {
  getAttribute: (name) => name === 'aria-expanded' ? 'true' : '',
  closest: () => null,
};
const composerRoot = { contains: (node) => node === trigger || node === composer };
const menu = {
  getAttribute: (name) => name === 'aria-labelledby' ? 'model-trigger' : '',
  hasAttribute: () => false,
  closest: () => menu,
  querySelector: (selector) => selector === '[data-model-picker-power-slider]' ? panel
    : selector === '[role="menuitemradio"]' ? radios[0]
      : selector.includes('[role="slider"]') ? slider : null,
  querySelectorAll: (selector) => selector === '[role="status"]' ? [status]
    : selector === '[data-model-picker-view-toggle="true"]' ? [toggle]
      : selector === '[role="menuitemradio"]' ? radios : [],
};
context.document = {
  activeElement: null,
  getElementById: () => trigger,
  querySelectorAll: (selector) => selector.startsWith('[role="menu"]') ? [menu] : [],
  dispatchEvent: () => {},
};
const commands = context.ChatGptIntelligenceCommands.createIntelligenceCommands({
  DOM_PARSER: context.ChatGptDomParserCore,
  isVisible: () => true,
  normalizeText: (text) => String(text).trim(),
  normalizeComparable: (text) => String(text).toLowerCase().trim(),
  unique: (values) => [...new Set(values)],
  findComposer: () => composer,
  findComposerRootStrict: () => composerRoot,
  isPrimaryChatSurfaceElement: () => true,
  delay: async () => {}, diagnostic: () => {},
});
const selected = commands.effortSliderOptions(menu).options;
assert.equal(selected.length, 1, 'Do not invent unobserved slider tiers');
assert.equal(selected[0].id, 'xhigh');
assert.equal(selected[0].selected, true);
assert.equal(commands.modelSubmenuOpener(menu), toggle);
statusText = 'High, 3 of 5.';
currentPosition = '2';
assert.equal(commands.effortSliderOptions(menu).options[0].id, 'high', 'High must remain distinct from Extra High');
currentPosition = '3';
assert.equal(commands.effortSliderOptions(menu).options.length, 0, 'Reject contradictory status and slider position');
statusText = 'Unrecognized tier, 4 of 5.';
assert.match(commands.effortSliderOptions(menu).options[0].id, /^effort-unrecognized-tier/, 'Unknown labels must remain opaque');
statusText = 'Extra High, 4 of 5.';
let state = await commands.readIntelligenceState();
assert.equal(state.selectedModel.label, 'GPT-6');
checkedModel = 1;
state = await commands.readIntelligenceState();
assert.equal(state.selectedModel.label, 'GPT-5.6 Sol', 'Read the actual checked model, never a requested model');
checkedModel = -1;
await assert.rejects(commands.readIntelligenceState(), /no explicit checked selection/);
console.log('PASS: exact Extra High/High and position, opaque unknown tier, hidden checked model changes, missing checked model rejected.');
