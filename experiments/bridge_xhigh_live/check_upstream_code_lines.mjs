// Browser-free extraction checks through the actual shared/content parser pair.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = process.argv[2] || '/private/tmp/mathagent-upstream-bridge';
const fixture = fs.readFileSync(path.join(root, 'test/responseParserDomFixture.test.js'), 'utf8');
const context = vm.createContext({ console,
  Node: { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_POSITION_FOLLOWING: 4, DOCUMENT_POSITION_PRECEDING: 2 },
  CSS: { escape: String }, window: { CSS: { escape: String } },
  location: { href: 'https://chatgpt.com/c/own-code-lines-fixture' },
  getComputedStyle: () => ({ display: 'block', visibility: 'visible', opacity: '1', position: 'static' }),
});
vm.runInContext(fixture.slice(fixture.indexOf('const ELEMENT_NODE'), fixture.indexOf('async function loadParser'))
  + '\nglobalThis.fixtureEl = el;', context);
for (const file of ['artifactParserCore.js', 'domParserCore.js', 'responseParserCore.js', 'content/responseDom.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'tools/chrome-bridge-extension', file), 'utf8'), context);
}
const el = context.fixtureEl;
const shared = context.ChatGptResponseParserCore;
const parser = context.ChatGptResponseDom.createResponseDom({
  DOM_PARSER: context.ChatGptDomParserCore, isVisible: () => true,
  normalizeText: (text) => String(text).trim(), visibleText: (node) => node.textContent || '',
});

for (const lines of [
  ['value = "sqrt(2)"', 'print(value)'],
  ['', '  if True:', '\tvalue = " spaces  "  ', '', '    print(value)', ''],
  ['literal \\sqrt{2}, <tag>, & and ``` stay exact', '', 'final'],
]) {
  const content = el('pre', { class: 'cm-content', 'data-language': 'python' },
    ...lines.map((line) => el('div', { class: 'cm-line' }, line ? el('span', {}, line) : el('br'))));
  const widget = el('pre', {}, el('div', { class: 'cm-editor' }, content));
  const response = el('div', { class: 'markdown' }, widget);
  const before = response.outerHTML;
  const expected = lines.join('\n');
  assert.equal(shared.codeTextFromElement(content), expected);
  const blocks = parser.extractResponseBlocks(response, () => false, parser.createResponseParserPass(response));
  const code = blocks.filter((block) => block.type === 'code_block');
  assert.equal(code.length, 1, 'the outer widget remains one atomic code block');
  assert.equal(code[0].code, expected, 'code keeps physical lines, blank lines, indentation and literal whitespace');
  assert.equal(code[0].language, 'python');
  const fence = '`'.repeat(Math.max(3, ...Array.from(expected.matchAll(/`+/g), (match) => match[0].length + 1)));
  assert.equal(code[0].markdown, `${fence}python\n${expected}${expected.endsWith('\n') ? '' : '\n'}${fence}`);
  assert.equal(response.outerHTML, before, 'never modify the source response DOM');
}

const plainText = '\n  literal\t  spaces\n\nfinal\n';
assert.equal(shared.codeTextFromElement(el('code', {}, plainText)), plainText, 'ordinary code stays literal');
assert.equal(shared.codeTextFromElement(el('pre', {}, 'a\r\nb\r')), 'a\nb\n', 'retain existing CR normalization');
console.log('PASS: actual shared/content parser preserves CodeMirror physical lines, blank lines, indentation, literal whitespace and fences; ordinary code and source DOM remain unchanged.');
