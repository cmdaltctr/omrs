"""Style sheet and script of the Experiment 35 blind labelling page.

Plain strings that ``labelpage35.write_page`` puts inline. Nothing here loads
a file, a font or a script from the network: the fonts are the system fonts.
The words "chunk", "score" and "verdict" stay out of this file, because the
page tests ban them (the page must stay blind).
"""

from __future__ import annotations

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f4f5f8; --card: #ffffff; --ink: #1b2130; --muted: #4b5468; --panel: #eef0f5;
  --line: #cfd5e1; --accent: #2a56c6; --on-accent: #ffffff; --done: #2c8f5a;
  --focus: #1a3fa0; --emphasis: #f3f6ff; --ring: rgba(42, 86, 198, 0.3);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151c; --card: #1a1f29; --ink: #e7eaf1; --muted: #aab3c4; --panel: #232a37;
    --line: #38414f; --accent: #86abff; --on-accent: #0a1226; --done: #4fc58b;
    --focus: #b4ccff; --emphasis: #202a3d; --ring: rgba(134, 171, 255, 0.35);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.bar {
  position: sticky; top: 0; z-index: 10; background: var(--card);
  border-bottom: 1px solid var(--line); box-shadow: 0 1px 6px rgba(0, 0, 0, 0.1);
}
.bar-inner {
  max-width: 820px; margin: 0 auto; padding: 10px 16px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
}
.bar h1 { flex: 1 1 8em; margin: 0; font-size: 1.15rem; }
.who { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 0.9rem; }
select {
  font: inherit; padding: 5px 8px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--card); color: var(--ink);
}
button {
  font: inherit; font-weight: 600; min-height: 36px; padding: 6px 14px; cursor: pointer;
  border: 1px solid var(--accent); border-radius: 8px; background: transparent; color: var(--accent);
}
button.primary { background: var(--accent); color: var(--on-accent); }
button:disabled { opacity: 0.5; cursor: default; }
button:focus-visible, select:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.progress { flex: 1 1 100%; order: 5; }
#progress-text { display: block; color: var(--muted); font-size: 0.85rem; margin-bottom: 4px; }
.track { height: 6px; border-radius: 3px; background: var(--panel); overflow: hidden; }
.fill { height: 100%; width: 0; background: var(--done); transition: width 0.2s; }
.page { max-width: 820px; margin: 0 auto; padding: 16px; }
.guide {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 8px 14px;
}
.guide summary { cursor: pointer; font-weight: 600; padding: 4px 0; }
.guide dt { font-weight: 700; margin-top: 8px; }
.guide dd { margin: 2px 0 0; color: var(--muted); }
.hint { margin: 10px 2px 0; color: var(--muted); font-size: 0.85rem; }
.card {
  background: var(--card); border: 2px solid var(--line); border-radius: 12px;
  padding: 16px; margin: 16px 0; scroll-margin-top: calc(var(--bar, 4rem) + 12px);
}
.card.done { border-color: var(--done); }
.card.current { box-shadow: 0 0 0 3px var(--ring); }
.card-head {
  margin: 0 0 10px; color: var(--muted); font-size: 0.8rem; font-weight: 700;
  letter-spacing: 0.05em; text-transform: uppercase;
}
.block { border-radius: 8px; padding: 10px 12px; margin: 0 0 10px; }
.context { background: var(--panel); color: var(--muted); }
.focus {
  background: var(--emphasis); border-left: 4px solid var(--accent);
  color: var(--ink); font-size: 1.15rem; font-weight: 500;
}
.tag {
  margin-bottom: 2px; color: var(--muted); font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
}
.text { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.passage {
  max-height: 16em; overflow: auto; margin: 0 0 10px; padding: 0 12px 10px;
  border: 1px solid var(--line); border-radius: 8px; background: var(--card);
  font-size: 0.95rem;
}
.passage .tag { position: sticky; top: 0; padding: 8px 0 4px; background: var(--card); }
.passage:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.choices { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 0; padding: 0; border: 0; min-width: 0; }
.pill { position: relative; flex: 1 1 8em; }
.pill input {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%; margin: 0;
  opacity: 0; cursor: pointer;
}
.face {
  display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px;
  padding: 8px 14px; border: 2px solid var(--line); border-radius: 999px;
  background: var(--card); font-weight: 600; text-align: center;
}
.pill:hover .face { border-color: var(--accent); }
.pill input:checked + .face { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.pill input:focus-visible + .face { outline: 3px solid var(--focus); outline-offset: 2px; }
.key { padding: 0 5px; border: 1px solid currentColor; border-radius: 4px; font-size: 0.75rem; opacity: 0.8; }
.sr {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
  white-space: nowrap;
}
@media (max-width: 560px) {
  .bar-inner { padding: 8px 12px; }
  .page { padding: 12px; }
  .card { padding: 12px; margin: 12px 0; }
  .focus { font-size: 1.05rem; }
  .pill { flex-basis: 100%; }
}
"""

SCRIPT = """
const data = JSON.parse(document.getElementById('items').textContent);
const store = 'exp35-draft-' + data.set;
let labels = {};
try { labels = JSON.parse(localStorage.getItem(store) || '{}'); } catch (e) { labels = {}; }
function keep() { try { localStorage.setItem(store, JSON.stringify(labels)); } catch (e) {} }
const total = data.items.length;
const root = document.getElementById('list');
const bar = document.getElementById('bar');
const progressText = document.getElementById('progress-text');
const fill = document.getElementById('progress-bar');
const track = document.getElementById('track');
const nextButton = document.getElementById('next');
const cards = [];
let current = 0;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) { node.className = cls; }
  if (text !== undefined) { node.textContent = text; }
  return node;
}
function isLabelled(i) { return Boolean(labels[data.items[i].item_id]); }

function showProgress() {
  let done = 0;
  cards.forEach(function (card, i) {
    const has = isLabelled(i);
    if (has) { done += 1; }
    card.node.classList.toggle('done', has);
  });
  const words = done + ' of ' + total + ' labelled';
  if (progressText.textContent !== words) { progressText.textContent = words; }
  fill.style.width = (total ? (100 * done) / total : 0) + '%';
  track.setAttribute('aria-valuenow', String(done));
  nextButton.disabled = done === total;
}
function showCurrent() {
  cards.forEach(function (card, i) { card.node.classList.toggle('current', i === current); });
}
function pick(i, c) {
  labels[data.items[i].item_id] = data.choices[c][0];
  cards[i].inputs[c].checked = true;
  current = i;
  keep();
  showProgress();
  showCurrent();
}
function goTo(i) {
  current = Math.max(0, Math.min(total - 1, i));
  cards[current].node.scrollIntoView({block: 'start'});
  showCurrent();
}

data.items.forEach(function (item, i) {
  const node = el('section', 'card');
  node.id = 'card-' + i;
  node.dataset.index = String(i);
  node.setAttribute('aria-labelledby', 'head-' + i);
  const head = el('h2', 'card-head', 'Item ' + (i + 1) + ' of ' + total);
  head.id = 'head-' + i;
  node.appendChild(head);
  data.layout.forEach(function (row) {
    const field = row[0];
    const label = row[1];
    const kind = row[2];
    const values = Array.isArray(item[field]) ? item[field] : [item[field]];
    values.forEach(function (value, k) {
      const tag = kind === 'passages' ? label + ' ' + (k + 1) : label;
      const box = el('div', kind === 'passages' ? 'passage' : 'block ' + kind);
      if (kind === 'passages') {
        box.tabIndex = 0;
        box.setAttribute('role', 'region');
        box.setAttribute('aria-label', tag);
      }
      box.appendChild(el('div', 'tag', tag));
      box.appendChild(el('p', 'text', value));
      node.appendChild(box);
    });
  });
  const group = el('fieldset', 'choices');
  group.appendChild(el('legend', 'sr', 'Label for item ' + (i + 1)));
  const inputs = [];
  data.choices.forEach(function (choice, c) {
    const pill = el('label', 'pill');
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = item.item_id;
    input.value = choice[0];
    input.checked = labels[item.item_id] === choice[0];
    input.addEventListener('change', function () { pick(i, c); });
    const face = el('span', 'face');
    face.appendChild(el('span', 'key', String(c + 1)));
    face.appendChild(el('span', 'word', choice[1]));
    pill.appendChild(input);
    pill.appendChild(face);
    group.appendChild(pill);
    inputs.push(input);
  });
  node.appendChild(group);
  node.addEventListener('focusin', function () { current = i; showCurrent(); });
  root.appendChild(node);
  cards.push({node: node, inputs: inputs});
});

nextButton.addEventListener('click', function () {
  for (let n = 1; n <= total; n += 1) {
    const i = (current + n) % total;
    if (!isLabelled(i)) { goTo(i); return; }
  }
});

document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) { return; }
  const target = e.target;
  if (target.tagName === 'SELECT' || target.tagName === 'TEXTAREA') { return; }
  const key = e.key;
  if (key >= '1' && key <= '9') {
    const c = Number(key) - 1;
    if (c >= data.choices.length) { return; }
    const host = target.closest ? target.closest('.card') : null;
    e.preventDefault();
    pick(host ? Number(host.dataset.index) : current, c);
    return;
  }
  const inPassage = target.closest && target.closest('.passage');
  if (key === 'j' || key === 'J' || (key === 'ArrowDown' && !inPassage)) {
    e.preventDefault();
    goTo(current + 1);
  } else if (key === 'k' || key === 'K' || (key === 'ArrowUp' && !inPassage)) {
    e.preventDefault();
    goTo(current - 1);
  }
});

let waiting = false;
window.addEventListener('scroll', function () {
  if (waiting) { return; }
  waiting = true;
  requestAnimationFrame(function () {
    waiting = false;
    const edge = bar.offsetHeight + 40;
    for (let i = 0; i < cards.length; i += 1) {
      if (cards[i].node.getBoundingClientRect().bottom > edge) { current = i; break; }
    }
    showCurrent();
  });
});
function sizeBar() { document.documentElement.style.setProperty('--bar', bar.offsetHeight + 'px'); }
window.addEventListener('resize', sizeBar);
sizeBar();

document.getElementById('save').addEventListener('click', function () {
  const who = document.getElementById('labeller').value;
  if (!who) { alert('Choose L1 or L2 first.'); return; }
  const mine = {};
  let open = 0;
  data.items.forEach(function (item) {
    if (labels[item.item_id]) { mine[item.item_id] = labels[item.item_id]; } else { open += 1; }
  });
  if (open > 0 && !confirm(open + ' of ' + total + ' items are unlabelled. Save anyway?')) { return; }
  const out = {set: data.set, labeller: who, labels: mine};
  const blob = new Blob([JSON.stringify(out, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = data.set + '-' + who + '.json';
  a.click();
});
showProgress();
showCurrent();
"""
