// Browser-free regression using upstream's existing DOM fixture helpers.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const fixture = fs.readFileSync(path.join(root, 'test/responseParserDomFixture.test.js'), 'utf8');
const context = vm.createContext({ console,
  Node: { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 },
  CSS: { escape: String }, window: { CSS: { escape: String } },
  location: { href: 'https://chatgpt.com/c/own-math-fixture' },
  getComputedStyle: () => ({ display: 'block', visibility: 'visible', opacity: '1', position: 'static' }),
});
vm.runInContext(fixture.slice(fixture.indexOf('const ELEMENT_NODE'), fixture.indexOf('async function loadParser')) + `
  globalThis.fixtureEl = el;
  globalThis.fixtureCode = codeWidget;
  FakeElement.prototype.replaceWith = function(text) {
    if (!this.parentElement) return;
    const parent = this.parentElement;
    const replacement = new FakeText(text);
    replacement.parentElement = parent;
    parent.childNodes[parent.childNodes.indexOf(this)] = replacement;
    this.parentElement = null;
  };
`, context);
for (const file of ['artifactParserCore.js', 'domParserCore.js', 'responseParserCore.js', 'content/responseDom.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'tools/chrome-bridge-extension', file), 'utf8'), context);
}
const el = context.fixtureEl;
function math(tex, display = false) {
  const body = el('span', { class: 'katex' },
    el('span', { class: 'katex-mathml' }, el('math', { display: display ? 'block' : 'inline' },
      el('semantics', {}, el('mrow', {}, '2pq2'), el('annotation', { encoding: 'application/x-tex' }, tex)))),
    el('span', { class: 'katex-html', 'aria-hidden': 'true' }, 'CORRUPTED_GLYPHS'));
  return display ? el('span', { class: 'katex-display' }, body) : body;
}
const radical = String.raw`\sqrt{2}`;
const fraction = String.raw`\sqrt{2}=\frac pq,`;
const exponent = String.raw`p^2=2q^2`;
const literal = String.raw`literal \sqrt{2}, p^2, <annotation encoding="application/x-tex">unchanged</annotation>`;
const response = el('div', { class: 'markdown' },
  el('p', {}, 'Theorem: ', math(radical), ' is irrational. ', el('code', {}, literal)),
  math(fraction, true),
  el('ul', {}, el('li', {}, 'Then ', math(exponent))),
  el('table', {}, el('tr', {}, el('th', {}, 'Formula')), el('tr', {}, el('td', {}, math(String.raw`n^{2}`)))),
  context.fixtureCode('Text', literal));
const before = response.outerHTML;
const parser = context.ChatGptResponseDom.createResponseDom({
  DOM_PARSER: context.ChatGptDomParserCore,
  isVisible: () => true,
  normalizeText: (text) => String(text).trim(),
  visibleText: (node) => node.textContent || '',
});
const blocks = parser.extractResponseBlocks(response, () => false, parser.createResponseParserPass(response));
const output = blocks.map((block) => block.markdown).join('\n\n');
assert.ok(output.includes(String.raw`\(\sqrt{2}\)`));
assert.ok(output.includes(`\\[\n${fraction}\n\\]`));
assert.ok(output.includes(`\\(${exponent}\\)`));
assert.ok(output.includes(String.raw`\(n^{2}\)`));
assert.ok(!output.includes('CORRUPTED_GLYPHS'));
const code = blocks.find((block) => block.type === 'code_block');
assert.equal(code.code, literal, 'Literal code fence content must remain verbatim');
assert.ok(output.includes('`' + literal + '`'), 'Inline code must remain literal');
assert.equal(response.outerHTML, before, 'Never modify the original response DOM');
console.log('PASS: KaTeX radicals/fractions/exponents survive inline/display/list/table extraction; code and original DOM remain unchanged.');
