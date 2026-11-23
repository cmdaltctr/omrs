"""Style sheet and script for the Experiment 35 blind labelling page.

The page follows the Experiment 34 review page: :func:`exp34_style` imports
that page's style block (imported, not copied, as the review-page pattern
asks), and ``CSS`` adds the labelling parts on top. Nothing here loads a file,
a font or a script from the network: fonts are system fonts. The words
"chunk", "score" and "verdict" stay out of this file, because the page tests
ban them (the page must stay blind).
"""

from __future__ import annotations

import sys
from pathlib import Path

EXP34 = Path(__file__).resolve().parent.parent / "34-worker-sample-review-2026-09-19"


def exp34_style() -> str:
    """Return the CSS of the Experiment 34 review page (``make_review.HTML_HEAD``)."""
    if str(EXP34) not in sys.path:
        sys.path.insert(0, str(EXP34))
    import make_review

    head = make_review.HTML_HEAD
    return head[head.index("<style>") + len("<style>") : head.index("</style>")]


CSS = """
.bar h1{font-size:1rem;margin:0 auto 0 0}
.who{font-size:.85rem;color:var(--muted);display:flex;gap:.35rem;align-items:center}
.who select{font:inherit;padding:.3rem .4rem;border:1px solid var(--line);border-radius:6px;
  background:var(--card);color:var(--ink)}
.bar button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.bar button:disabled{opacity:.5;cursor:default}
#progress{font-size:.95rem;font-weight:700;color:var(--ink);background:var(--soft);
  border:1px solid var(--line);border-radius:999px;padding:.25rem .8rem}
#progress.ok{color:#fff;background:var(--ok);border-color:var(--ok)}
#autosave{font-size:.8rem;color:var(--prob)}
.intro b{color:var(--ink)}
details.page{scroll-margin-top:calc(var(--bar,3.5rem) + .5rem)}
details.page>summary{flex-wrap:nowrap}
.qs{flex:1 1 0;min-width:0;color:var(--muted);font-size:.88rem;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.pstat{white-space:nowrap}
.pstat:empty{display:none}
details.page[data-done] .pstat{color:#fff;background:var(--ok);border-radius:999px;
  padding:.12rem .6rem;font-size:.74rem;font-weight:700}
details.page[data-done]{border-color:var(--ok)}
details.page[data-done]>summary{background:color-mix(in srgb,var(--ok) 12%,transparent)}
details.page[data-done]>summary .pt{color:var(--ok)}
.stick{top:calc(var(--bar,3.5rem) + .5rem);max-height:calc(100vh - var(--bar,3.5rem) - 1.5rem);
  overflow:auto;padding-right:.2rem}
.tag{font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);margin:0 0 .25rem}
.blk{margin-bottom:.8rem}
.ctx p{margin:.15rem 0;max-height:30vh;overflow:auto}
.ctx p,.focus,.md p,.md li,.qs{overflow-wrap:anywhere}
main{padding-bottom:60vh}
.outwrap{padding:0;margin-bottom:.8rem}
.viewbar{align-items:center}
.viewbar .tag{margin:0 auto 0 0}
.md{position:relative}
.md ul,.md ol{margin:.2rem 0;padding-left:1.3rem;font-size:.88rem}
.md li{margin:.1rem 0}
.md hr{border:0;border-top:1px solid var(--line)}
.ans .md{max-height:50vh}
details.psg .outwrap{padding:0 .6rem .6rem}
details.psg .md,details.psg .raw{max-height:40vh}
.cite{color:var(--muted);font-size:.8em;white-space:nowrap}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85em;
  background:var(--soft);border:1px solid var(--line);border-radius:4px;padding:0 .25em}
pre.code{font:.8rem/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre;
  overflow-x:auto;background:var(--soft);border:1px solid var(--line);border-radius:6px;
  padding:.55rem .75rem;margin:.4rem 0;tab-size:4}
pre.code code{font-size:inherit;background:none;border:0;padding:0}
pre.code.meta{font-size:.72rem;color:var(--muted);padding:.35rem .6rem}
mark.target{background:#ffe08a;color:inherit;border-radius:3px;padding:0 .1em;
  box-shadow:0 0 0 2px #ffe08a}
@media (prefers-color-scheme:dark){mark.target{background:#6b5200;box-shadow:0 0 0 2px #6b5200}
  .bar button.primary{color:#0b1020}}
.focus{font-size:1.2rem;font-weight:400;line-height:1.55;margin:0 0 1rem;padding:.8rem 1rem;
  background:var(--soft);border:1px solid var(--accent);border-radius:8px}
.focus strong{font-weight:700}
.judge .ans .md{max-height:60vh}
fieldset.form{border:1px solid var(--line);border-radius:8px;padding:.8rem;display:grid;gap:.6rem}
fieldset.form legend{font-weight:600;font-size:.92rem;padding:0 .3rem}
.judge .chip span{font-size:.95rem;padding:.5rem .95rem}
.chip{--pick:var(--accent)}
.chip:has(input[value=factual]),.chip:has(input[value=supported]),
.chip:has(input[value=correct]){--pick:#1f9d55}
.chip:has(input[value=refusal]),.chip:has(input[value=not_supported]),
.chip:has(input[value=not_correct]){--pick:#d64545}
.chip:has(input[value=mixed]){--pick:#2f6fdb}
.chip:has(input[value=cant_tell]){--pick:#e07b00}
.chip:hover span{border-color:var(--pick)}
.chip input:checked+span{background:var(--pick);border-color:var(--pick);color:#fff}
.chip input:focus-visible+span{outline:2px solid var(--pick);outline-offset:2px}
kbd{font:inherit;font-size:.72rem;border:1px solid currentColor;border-radius:4px;
  padding:0 .3rem;margin-right:.3rem;opacity:.75}
.note{font:inherit;font-size:.85rem;padding:.4rem .55rem;border:1px solid var(--line);
  border-radius:6px;background:var(--card);color:var(--ink)}
@media (max-width:900px){.body{grid-template-columns:minmax(0,1fr)}
  .stick{max-height:none;overflow:visible;padding-right:0}}
@media (max-width:560px){.bar h1{flex-basis:100%}.focus{font-size:1.08rem}
  .judge .chip{flex:1 1 100%}.judge .chip span{display:block}}
"""

SCRIPT = """
const data = JSON.parse(document.getElementById('items').textContent);
const store = 'exp35-draft-' + data.set;
const total = data.items.length;
let labels = {};
let notes = {};
try { labels = JSON.parse(localStorage.getItem(store) || '{}') || {}; } catch (e) { labels = {}; }
try { notes = JSON.parse(localStorage.getItem(store + '-notes') || '{}') || {}; } catch (e) { notes = {}; }
const autosave = document.getElementById('autosave');
function keep() {
  try { localStorage.setItem(store, JSON.stringify(labels)); localStorage.setItem(store + '-notes', JSON.stringify(notes)); } catch (e) { autosave.hidden = false; }
}
const cards = Array.from(document.querySelectorAll('details.page'));
const bar = document.getElementById('bar');
const progress = document.getElementById('progress');
const nextButton = document.getElementById('next');
let current = 0;

function idOf(i) { return data.items[i].item_id; }
function refresh() {
  let n = 0;
  cards.forEach(function (card, i) {
    const done = Boolean(labels[idOf(i)]);
    if (done) { n += 1; card.dataset.done = '1'; } else { delete card.dataset.done; }
    card.querySelector('.pstat').textContent = done ? '\\u2713 labelled' : '';
  });
  progress.textContent = 'Done ' + n + ' / ' + total;
  progress.classList.toggle('ok', n === total);
  nextButton.disabled = n === total;
}
function pick(i, c) {
  labels[idOf(i)] = data.choices[c][0];
  const inputs = cards[i].querySelectorAll('.chip input');
  inputs.forEach(function (input, k) { input.checked = k === c; });
  keep();
  refresh();
}
function showTarget(card) {
  const mark = card.querySelector('mark.target');
  if (!mark) { return; }
  const pane = mark.closest('.md');
  pane.scrollTop = Math.max(0, mark.offsetTop - pane.clientHeight / 3);
}
function goTo(i) {
  const card = cards[Math.max(0, Math.min(total - 1, i))];
  if (card.open) { card.scrollIntoView({block: 'start'}); } else { card.open = true; }
}

cards.forEach(function (card, i) {
  const inputs = card.querySelectorAll('.chip input');
  inputs.forEach(function (input, c) {
    input.name = 'pick-' + i;
    input.checked = labels[idOf(i)] === input.value;
    input.addEventListener('change', function () { pick(i, c); });
  });
  const note = card.querySelector('.note');
  note.value = notes[idOf(i)] || '';
  note.addEventListener('input', function () {
    if (note.value.trim()) { notes[idOf(i)] = note.value; } else { delete notes[idOf(i)]; }
    keep();
  });
  card.querySelector('.clear').addEventListener('click', function () {
    delete labels[idOf(i)];
    inputs.forEach(function (input) { input.checked = false; });
    keep();
    refresh();
  });
  card.addEventListener('toggle', function () {
    if (!card.open) { return; }
    current = i;
    cards.forEach(function (o) { if (o !== card && o.open) { o.open = false; } });
    card.scrollIntoView({block: 'start'});
    showTarget(card);
  });
});

document.addEventListener('click', function (e) {
  const button = e.target.closest('.vt');
  if (!button) { return; }
  const wrap = button.closest('.outwrap');
  const raw = wrap.querySelector('.raw');
  wrap.querySelectorAll('.vt').forEach(function (b) { b.classList.toggle('on', b === button); });
  if (button.dataset.v === 'raw' && !raw.textContent) {
    let value = data.items[Number(wrap.closest('details.page').dataset.i)][wrap.dataset.f];
    if (wrap.dataset.k !== undefined) { value = value[Number(wrap.dataset.k)]; }
    raw.textContent = typeof value === 'string' ? value : value.text;
  }
  wrap.querySelector('.md').hidden = button.dataset.v !== 'md';
  raw.hidden = button.dataset.v !== 'raw';
});

nextButton.addEventListener('click', function () {
  for (let n = 1; n <= total; n += 1) {
    const i = (current + n) % total;
    if (!labels[idOf(i)]) { goTo(i); return; }
  }
});
document.getElementById('collapse').addEventListener('click', function () {
  cards.forEach(function (card) { card.open = false; });
});

document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) { return; }
  const tag = e.target.tagName;
  if (tag === 'SELECT' || tag === 'TEXTAREA' || (tag === 'INPUT' && e.target.type === 'text')) { return; }
  const key = e.key;
  if (key >= '1' && key <= '9') {
    const c = Number(key) - 1;
    if (c >= data.choices.length || !cards[current].open) { return; }
    e.preventDefault();
    pick(current, c);
  } else if (key === 'j' || key === 'J') {
    e.preventDefault();
    goTo(current + 1);
  } else if (key === 'k' || key === 'K') {
    e.preventDefault();
    goTo(current - 1);
  }
});

function sizeBar() { document.documentElement.style.setProperty('--bar', bar.offsetHeight + 'px'); }
window.addEventListener('resize', sizeBar);
sizeBar();

document.getElementById('save').addEventListener('click', function () {
  const who = document.getElementById('labeller').value;
  if (!who) { alert('Choose L1 or L2 first.'); return; }
  const mine = {};
  const kept = {};
  let open = 0;
  data.items.forEach(function (item) {
    if (labels[item.item_id]) { mine[item.item_id] = labels[item.item_id]; } else { open += 1; }
    if (notes[item.item_id]) { kept[item.item_id] = notes[item.item_id]; }
  });
  if (open > 0 && !confirm(open + ' of ' + total + ' items are unlabelled. Save anyway?')) { return; }
  const out = {set: data.set, labeller: who, labels: mine, notes: kept};
  const blob = new Blob([JSON.stringify(out, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = data.set + '-' + who + '.json';
  a.click();
});
refresh();
"""
