"""Reading aid, labeller highlights and the relevance-audit set for the Experiment 35 page.

Pre-registration section 11.3 (A18, 2026-11-27). The reading aid marks the words
and numbers that occur both in the item text and in the text it is judged
against. Code only: the page script reads the rendered text, no model and no
network. The labeller can also highlight text in the passage and answer boxes;
those marks are a second colour and are saved with the label.

The relevance audit (H3) shows the question, the dataset's reference answer and
the unit text. The audit items file has no arm and the page never shows one:
``labelpage35.page_items`` keeps only the fields listed in ``AUDIT_FIELDS``.
"""

# ruff: noqa: E501
# (the page script below is JavaScript with long lines)
from __future__ import annotations

import json

#: Words the reading aid skips (it also skips tokens under 3 characters, except numbers).
STOP_WORDS = (
    "the and for are but not you all can was one our out has have had his her how its may who "
    "did any been this that with from they will would there their what when which were than "
    "then them these those into also such about more some other"
).split()

#: Which item fields carry the aid roles, per set: (item text, text it is judged against).
AID_ROLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "claim_kinds": (("claim",), ("passages",)),
    "faithfulness": (("claim",), ("passages",)),
    "correctness": (("answer",), ("reference",)),
    "relevance_audit": (("reference",), ("unit_text",)),
}

AUDIT_QUESTION = "Does this passage contain information that the reference answer uses?"
AUDIT_CHOICES = (
    ("relevant", "Relevant"),
    ("not_relevant", "Not relevant"),
    ("cant_tell", "Can't tell"),
)
AUDIT_FIELDS = ("question", "reference", "unit_text")
AUDIT_LAYOUT = (
    ("question", "Question", "context"),
    ("reference", "Reference answer", "block"),
    ("unit_text", "Unit text", "unit"),
)
AUDIT_GUIDANCE = (
    (
        "relevant",
        "The unit text holds information that the reference answer uses: a fact, a number or "
        "a step the reference answer states. You need no domain knowledge: compare the two texts.",
        'Reference: "Revenue was $5 million." Unit text: "Revenue reached $5 million in 2019."',
    ),
    (
        "not_relevant",
        "The unit text holds nothing that the reference answer uses, even if it is on the same "
        "topic.",
        'Reference: "Revenue was $5 million." Unit text: "The firm moved its office in 2019."',
    ),
    (
        "cant_tell",
        "Use this rarely. Choose it only when you cannot read the unit text or the reference "
        "answer well enough to compare them.",
        "The unit text is cut off after one word.",
    ),
)

INSTRUCTIONS_HTML = (
    "<h2>Reading aid and highlighting</h2><ul>"
    "<li>Blue words and numbers occur in both the item text and the text it is judged "
    "against. The aid is a reading help: it does not tell you the answer. Each item has a "
    "Reading aid button. It starts on. Click it to switch the aid off or on for that item; the "
    "page saves the state with your label.</li>"
    "<li>To highlight, select text in a passage or answer box (Rendered view) and click "
    "Highlight, or press H. The text turns pink. Click a highlight to remove it. The page "
    "saves your highlights with your label.</li></ul>"
)

CSS_AIDS = """
mark.aid{background:#cfe6ff;color:inherit;border-radius:3px;padding:0 .08em}
mark.hl{background:#ffc9e0;color:inherit;border-radius:3px;cursor:pointer;
  box-shadow:0 0 0 1px #e58fb5}
@media (prefers-color-scheme:dark){mark.aid{background:#1d4a7a}mark.hl{background:#7a2d52;
  box-shadow:0 0 0 1px #b4558a}}
.aids{display:flex;gap:.5rem;flex-wrap:wrap;margin:0 0 .8rem}
.aids button{font:inherit;font-size:.82rem;padding:.3rem .7rem;border:1px solid var(--line);
  border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
.aidbtn[aria-pressed=true]{background:#cfe6ff;border-color:#7fb2ee;color:#0b1020}
.mlbanner{font-size:.8rem;font-weight:700;color:#0b1020;background:#f2c94c;border-radius:999px;
  padding:.2rem .7rem}
"""

#: Pure functions of the reading aid (no DOM). The tests run them in node.
AID_CORE_JS = (
    r"""
const AID_STOP = new Set(__STOP__);
const AID_RE = /\$?\d+(?:[.,]\d+)*|[\p{L}\p{N}]+/gu;
function aidEligible(tok) {
  return /^\$?\d/.test(tok) || (tok.length >= 3 && !AID_STOP.has(tok));
}
function aidTokens(text) {
  const out = new Set();
  (text.toLowerCase().match(AID_RE) || []).forEach(function (t) {
    if (aidEligible(t)) { out.add(t); }
  });
  return out;
}
function aidShared(a, b) {
  const right = aidTokens(b);
  const out = new Set();
  aidTokens(a).forEach(function (t) { if (right.has(t)) { out.add(t); } });
  return out;
}
function aidSegments(text, shared) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(AID_RE)) {
    if (m.index > last) { out.push({t: text.slice(last, m.index), hit: false}); }
    out.push({t: m[0], hit: shared.has(m[0].toLowerCase())});
    last = m.index + m[0].length;
  }
  if (last < text.length) { out.push({t: text.slice(last), hit: false}); }
  return out;
}
""".replace("__STOP__", json.dumps(STOP_WORDS))
)

#: The page part: aid toggle, highlights, draft restore and the extra saved fields.
SCRIPT_AIDS = (
    AID_CORE_JS
    + r"""
let highlights = {};
let aidOn = {};
try { highlights = JSON.parse(localStorage.getItem(store + '-hl') || '{}') || {}; } catch (e) { highlights = {}; }
try { aidOn = JSON.parse(localStorage.getItem(store + '-aid') || '{}') || {}; } catch (e) { aidOn = {}; }
function keepAids() {
  try {
    localStorage.setItem(store + '-hl', JSON.stringify(highlights));
    localStorage.setItem(store + '-aid', JSON.stringify(aidOn));
  } catch (e) { autosave.hidden = false; }
}
function textNodes(root) {
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) { out.push(node); node = walker.nextNode(); }
  return out;
}
function aidRoots(card, role) {
  return Array.from(card.querySelectorAll('[data-aid="' + role + '"]')).map(function (el) {
    return el.classList.contains('outwrap') ? el.querySelector('.md') : el;
  });
}
function unwrap(card, selector) {
  card.querySelectorAll(selector).forEach(function (m) {
    const parent = m.parentNode;
    while (m.firstChild) { parent.insertBefore(m.firstChild, m); }
    parent.removeChild(m);
    parent.normalize();
  });
}
function applyAid(card) {
  const mine = aidRoots(card, 'item');
  const other = aidRoots(card, 'against');
  const text = function (roots) { return roots.map(function (r) { return r.textContent; }).join(' '); };
  const shared = aidShared(text(mine), text(other));
  mine.concat(other).forEach(function (root) {
    textNodes(root).forEach(function (node) {
      const parts = aidSegments(node.nodeValue, shared);
      if (!parts.some(function (p) { return p.hit; })) { return; }
      const frag = document.createDocumentFragment();
      parts.forEach(function (p) {
        if (!p.hit) { frag.appendChild(document.createTextNode(p.t)); return; }
        const mark = document.createElement('mark');
        mark.className = 'aid';
        mark.textContent = p.t;
        frag.appendChild(mark);
      });
      node.parentNode.replaceChild(frag, node);
    });
  });
}
function areaOf(wrap) { return wrap.dataset.f + (wrap.dataset.k !== undefined ? ':' + wrap.dataset.k : ''); }
function areaRoot(card, area) {
  const wraps = Array.from(card.querySelectorAll('.outwrap'));
  const wrap = wraps.find(function (w) { return areaOf(w) === area; });
  return wrap ? wrap.querySelector('.md') : null;
}
function wrapOffsets(root, start, end, idx) {
  let pos = 0;
  const todo = [];
  textNodes(root).forEach(function (node) {
    const len = node.nodeValue.length;
    if (pos < end && pos + len > start) { todo.push([node, Math.max(start, pos) - pos, Math.min(end, pos + len) - pos]); }
    pos += len;
  });
  todo.forEach(function (t) {
    const range = document.createRange();
    range.setStart(t[0], t[1]);
    range.setEnd(t[0], t[2]);
    const mark = document.createElement('mark');
    mark.className = 'hl';
    mark.dataset.h = String(idx);
    range.surroundContents(mark);
  });
}
function paint(card, i) {
  const id = idOf(i);
  unwrap(card, 'mark.aid');
  unwrap(card, 'mark.hl');
  (highlights[id] || []).forEach(function (h, idx) {
    const root = areaRoot(card, h.area);
    if (root) { wrapOffsets(root, h.start, h.start + h.text.length, idx); }
  });
  if (aidOn[id] !== false) { applyAid(card); }
  const button = card.querySelector('.aidbtn');
  button.textContent = 'Reading aid: ' + (aidOn[id] !== false ? 'on' : 'off');
  button.setAttribute('aria-pressed', String(aidOn[id] !== false));
}
function highlight() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) { return; }
  const range = sel.getRangeAt(0);
  const anchor = range.commonAncestorContainer;
  const root = (anchor.nodeType === 1 ? anchor : anchor.parentElement).closest('.outwrap .md');
  if (!root) { return; }
  const card = root.closest('details.page');
  const i = Number(card.dataset.i);
  const before = document.createRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const text = range.toString();
  if (!text.trim()) { return; }
  const id = idOf(i);
  highlights[id] = (highlights[id] || []).concat([{area: areaOf(root.closest('.outwrap')), text: text, start: before.toString().length}]);
  sel.removeAllRanges();
  keepAids();
  paint(card, i);
}
function extraSave(mine) {
  const aid = {};
  const marks = {};
  data.items.forEach(function (item) {
    const id = item.item_id;
    if (mine[id]) { aid[id] = aidOn[id] !== false; }
    if (highlights[id] && highlights[id].length) { marks[id] = highlights[id]; }
  });
  const out = {reading_aid: aid, highlights: marks};
  if (data.model_labeller) { out.model_labeller = true; }
  return out;
}

cards.forEach(function (card, i) {
  card.addEventListener('toggle', function () { if (card.open && !card.dataset.painted) { card.dataset.painted = '1'; paint(card, i); } });
  card.querySelector('.aidbtn').addEventListener('click', function () {
    aidOn[idOf(i)] = aidOn[idOf(i)] === false;
    keepAids();
    paint(card, i);
  });
  const hlButton = card.querySelector('.hlbtn');
  hlButton.addEventListener('mousedown', function (e) { e.preventDefault(); });
  hlButton.addEventListener('click', highlight);
});
document.addEventListener('click', function (e) {
  const mark = e.target.closest('mark.hl');
  if (!mark) { return; }
  const sel = window.getSelection();
  if (sel && !sel.isCollapsed) { return; }
  const card = mark.closest('details.page');
  const i = Number(card.dataset.i);
  highlights[idOf(i)].splice(Number(mark.dataset.h), 1);
  if (!highlights[idOf(i)].length) { delete highlights[idOf(i)]; }
  keepAids();
  paint(card, i);
});
document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) { return; }
  const tag = e.target.tagName;
  if (tag === 'SELECT' || tag === 'TEXTAREA' || (tag === 'INPUT' && e.target.type === 'text')) { return; }
  if (e.key === 'h' || e.key === 'H') { e.preventDefault(); highlight(); }
});
"""
)


def aids_row() -> str:
    """The two buttons under each item: the reading aid toggle and Highlight."""
    return (
        '<div class="aids"><button type="button" class="aidbtn" aria-pressed="true">'
        'Reading aid: on</button><button type="button" class="hlbtn">Highlight (H)</button></div>'
    )


def aid_attr(set_name: str, field: str) -> str:
    """The ``data-aid`` attribute for *field* of *set_name* (empty when it takes no part)."""
    item_fields, against_fields = AID_ROLES[set_name]
    if field in item_fields:
        return ' data-aid="item"'
    if field in against_fields:
        return ' data-aid="against"'
    return ""
