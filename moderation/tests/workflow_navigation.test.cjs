const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const script = readFileSync(join(__dirname, '../static/moderation/app.js'), 'utf8');

function page(search, storage, failStorage = false) {
  const clicked = {}, restored = [], classes = new Set();
  const link = {dataset: {gridCell: 'submission:readable'}, classList: {add: x => classes.add(x), remove: x => classes.delete(x)}, addEventListener: (event, callback) => {clicked[event] = callback;}};
  const table = {scrollLeft: 640};
  const panel = {dataset: {gridReview: 'review-id', savedCell: 'submission:readable'}, querySelector: () => table, querySelectorAll: () => [link]};
  const context = {
    document: {querySelectorAll: () => [], querySelector: selector => selector === '[data-grid-review]' ? panel : null},
    window: {location: {search, hash: ''}, scrollY: 740, scrollX: 0, scrollTo: (...args) => restored.push(args), setTimeout: () => {}},
    sessionStorage: {getItem: key => {if(failStorage) throw Error('Storage blocked'); return storage.get(key) || null;}, setItem: (key, value) => {if(failStorage) throw Error('Storage blocked'); storage.set(key, value);}},
    URL, URLSearchParams, requestAnimationFrame: callback => callback(),
  };
  vm.runInNewContext(script, context);
  return {clicked, table, restored, classes};
}

test('returning from a saved decision restores both scroll positions with equivalent filters', () => {
  const storage = new Map();
  const grid = page('?sort=number&needs_review=on', storage);
  grid.clicked.click();
  const returned = page('?needs_review=on&sort=number&saved=submission%3Areadable', storage);
  assert.equal(returned.table.scrollLeft, 640);
  assert.equal(returned.restored.length, 1);
  assert.equal(returned.restored[0][1], 740);
  assert.ok(returned.classes.has('decision-saved'));
});

test('changing filters does not restore an unrelated grid position', () => {
  const storage = new Map();
  page('?sort=number', storage).clicked.click();
  assert.equal(page('?sort=name', storage).restored.length, 0);
});

test('disabled browser storage does not break navigation', () => {
  const grid = page('?sort=number', new Map(), true);
  assert.doesNotThrow(() => grid.clicked.click());
});


function feedbackPage(current, canCopy = true) {
  let handler, copied = '', selected = false, verified = false;
  const area = {value: 'Final reviewed feedback', select: () => {selected = true;}};
  const status = {textContent: ''};
  const button = {dataset: {verifyUrl: '/reviews/test/feedback/?verify=signature'}, addEventListener: (_event, callback) => {handler = callback;}};
  const context = {
    document: {querySelectorAll: selector => selector === '[data-copy-feedback]' ? [button] : [], querySelector: selector => selector === '[data-copy-feedback]' ? button : selector === '[data-copy-status]' ? status : null, getElementById: () => area},
    window: {location: {hash: ''}},
    navigator: {clipboard: canCopy ? {writeText: async text => {assert.ok(verified); copied = text;}} : undefined},
    fetch: async () => {verified = true; return {ok: true, json: async () => ({current})};},
  };
  vm.runInNewContext(script, context);
  return {click: () => handler(), area, status, button, get copied() {return copied;}, get selected() {return selected;}};
}

test('only current completed feedback is copied', async () => {
  const page = feedbackPage(true);
  await page.click();
  assert.equal(page.copied, 'Final reviewed feedback');
  assert.match(page.status.textContent, /Feedback copied/);
});

test('changed moderation prevents stale feedback copying', async () => {
  const page = feedbackPage(false);
  await page.click();
  assert.equal(page.copied, '');
  assert.equal(page.area.value, '');
  assert.equal(page.button.disabled, true);
});

test('clipboard fallback selects only verified current feedback', async () => {
  const page = feedbackPage(true, false);
  await page.click();
  assert.ok(page.selected);
  assert.match(page.status.textContent, /Ctrl\+C/);
});


test('bulk copy buttons each use their own feedback block and verification', async () => {
  const handlers = [], copied = [], requested = [];
  const areas = {first: {value: 'Student A feedback'}, second: {value: 'Student B feedback'}, statusA: {textContent: ''}, statusB: {textContent: ''}};
  const buttons = [
    {dataset: {feedbackTarget: 'first', statusTarget: 'statusA', verifyUrl: '/feedback/a'}, addEventListener: (_e, fn) => {handlers[0] = fn;}},
    {dataset: {feedbackTarget: 'second', statusTarget: 'statusB', verifyUrl: '/feedback/b'}, addEventListener: (_e, fn) => {handlers[1] = fn;}},
  ];
  vm.runInNewContext(script, {
    document: {querySelectorAll: selector => selector === '[data-copy-feedback]' ? buttons : [], querySelector: () => null, getElementById: id => areas[id]},
    window: {location: {hash: ''}},
    fetch: async url => {requested.push(url); return {ok: true, json: async () => ({current: true})};},
    navigator: {clipboard: {writeText: async text => {copied.push(text);}}},
  });
  await handlers[1]();
  assert.deepEqual(copied, ['Student B feedback']);
  assert.deepEqual(requested, ['/feedback/b']);
  assert.equal(areas.statusA.textContent, '');
  assert.match(areas.statusB.textContent, /Feedback copied/);
});


test('column headings toggle sorting and retain existing filters', () => {
  let click, assigned;
  const button = {dataset: {sort: 'overall'}, addEventListener: (_event, fn) => {click = fn;}};
  const run = href => vm.runInNewContext(script, {
    document: {querySelectorAll: selector => selector === '[data-sort]' ? [button] : [], querySelector: () => null},
    window: {location: {href, hash: '', assign: url => {assigned = String(url);}}},
    URL,
  });
  run('http://localhost/reviews/test/?q=student&needs_review=on&sort=overall&direction=asc');
  click();
  const result = new URL(assigned);
  assert.equal(result.searchParams.get('sort'), 'overall');
  assert.equal(result.searchParams.get('direction'), 'desc');
  assert.equal(result.searchParams.get('q'), 'student');
  assert.equal(result.searchParams.get('needs_review'), 'on');
  button.dataset.sort = 'name';
  run('http://localhost/reviews/test/');
  click();
  assert.equal(new URL(assigned).searchParams.get('direction'), 'desc');
});


test('only the active rule automatically expands its supporting evidence', () => {
  const hashHandlers = {};
  const frames = [];
  const scrolled = [];
  const makeFinding = id => {
    const handlers = {};
    const evidence = {open: false};
    return {id, evidence, handlers, scrollIntoView: options => {scrolled.push([id, options.block, evidence.open]);}, querySelector: selector => selector === '.evidence' ? evidence : selector === 'summary' ? {addEventListener: (_event, callback) => {handlers.click = callback;}} : selector === '.decision-form' ? {addEventListener: (_event, callback) => {handlers.focus = callback;}} : {focus: () => {}}};
  };
  const first = makeFinding('first');
  const second = makeFinding('second');
  const findings = [first, second];
  const location = {hash: '#first'};
  vm.runInNewContext(script, {
    document: {querySelectorAll: selector => selector === '.finding' ? findings : [], querySelector: () => null, getElementById: id => findings.find(f => f.id === id)},
    window: {location, requestAnimationFrame: callback => frames.push(callback), addEventListener: (event, callback) => {hashHandlers[event] = callback;}},
  });
  assert.equal(first.evidence.open, true);
  assert.equal(second.evidence.open, false);
  assert.equal(scrolled.length, 0);
  frames.shift()();
  assert.deepEqual(scrolled, [['first', 'start', true]]);
  second.handlers.focus();
  assert.equal(first.evidence.open, false);
  assert.equal(second.evidence.open, true);
  second.evidence.open = false;
  second.handlers.focus();
  assert.equal(second.evidence.open, false);
  location.hash = '#first';
  hashHandlers.hashchange();
  frames.shift()();
  assert.equal(scrolled.length, 2);
  assert.equal(first.evidence.open, true);
  assert.equal(second.evidence.open, false);
});

test('audit shortcut fills blanks without changing recorded exceptions', () => {
  let click;
  const complete = {checked: false};
  const exceptionComplete = {checked: false};
  const exception = {checked: true};
  const rows = [
    {querySelector: selector => selector === 'input:checked' ? null : complete},
    {querySelector: selector => selector === 'input:checked' ? exception : exceptionComplete},
  ];
  const button = {addEventListener: (_event, callback) => {click = callback;}};
  vm.runInNewContext(script, {
    document: {
      querySelector: selector => selector === '[data-audit-complete]' ? button : null,
      querySelectorAll: selector => selector === '[data-audit-row]' ? rows : [],
    },
  });
  assert.equal(complete.checked, false);
  click();
  assert.equal(complete.checked, true);
  assert.equal(exceptionComplete.checked, false);
  assert.equal(exception.checked, true);
});
