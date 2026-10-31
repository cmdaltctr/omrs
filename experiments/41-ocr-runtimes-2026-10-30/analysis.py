"""Experiment 41 analysis: page similarity of an arm against a baseline arm.

    analysis.py --arm D4              # against D0 (dots.mocr) or P0 (PaddleOCR-VL)
    analysis.py --arm D4 --baseline D2    # matched-runtime pair, reported only

For every page both arms have text for, the script computes the token Dice coefficient with
the Experiment 33 tokeniser (``build_labels.tokens``, imported by path), then reports the
median, the share below 0.9, the 20 lowest pages and the formulas the arm altered or lost.
It writes ``output/similarity_<arm>_vs_<baseline>.json``. A baseline page without text (P0 had
36) and an arm page without a file (timeout, not yet run) are counted and skipped.

``review_list`` is the page selection of DR-3. ``--review`` is the review step (task 6.2):

    analysis.py --review              # all four arms (D4, D2, P4, P2)
    analysis.py --review --arm D4     # one arm

It runs the Experiment 37 noise screen (``make_noise_review.py``, imported by path after a
SHA-256 check) over the arm's E-maths and E-scan pages, selects the pages with ``review_list``
and writes ``output/review_<arm>.html`` and ``output/review_selection.json``. A page without
text (timeout, empty, error) is listed in the summary and not reviewed. Each page downloads
only its own arm: ``{"verdicts": {"<arm>": {"<page>": {"verdict", "note"}}}}``.

Run the plain similarity mode with any Python 3.11 or later (no third-party code). Run
``--review`` with the engine interpreter ``~/.omrs/ocr-workers/engines/paddleocr-vl/.venv/bin/python``
and ``PYTHONPATH=src`` (it has pypdf, pypdfium2 and, with ``src``, the Experiment 34 renderer).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import random
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ocr  # noqa: E402 - same folder; shared paths and page helpers

EXP33 = run_ocr.WORKTREE / "experiments/33-ocr-routing-natural-positive-2026-09-17"
EXP33_REL = "../33-ocr-routing-natural-positive-2026-09-17"
EXP34_REL = "../34-worker-sample-review-2026-09-19"
BUILD_LABELS_SHA256 = "4d9faa5437ee02d3de256a0fea156f9b02942e1798e2784a4f022497ac1ba2fa"
SEED = 41

# ruff: noqa: E501 - the pinned SHA-256 table below has lines longer than 100 characters

#: SHA-256 of every Experiment 37 and 33 input this experiment reads (OI-7), taken 2026-10-30.
#: A folder entry is the SHA-256 of ``<relative path>\0<file sha>\n`` lines for its files.
PINNED = {
    "sources.json": "d616b2de351d8e3307c5053f7760838c008d619a5866e1de1b7c29001b005df3",
    "maths_labels.json": "324ef438171c27ad388130691f4e9bbc0e29d69e320f38495732e99c5fc8ffbc",
    "noise_verdicts.json": "3f3a3cd2e4a6dc5766980e73a34501f9b055ffbbeb14772e6f99aa7575946634",
    "plan.json": "6c69907f3726841d0a1c7a9e28efbde4f32988a61596c7f6729f3dddae13ed63",
    "score_recall.py": "ee09cea51bfebce81205c42f9fd7227cdbc4d37ba467990fd2bb986c06d9e5e2",
    "check_katex.mjs": "3db2a9cf501ba4d6269720b88d990c766d2232f02db673d963c563ba5faae261",
    "output/ocr_state_dots-mocr.json": "6bafafaf4b2a3db4a250f68bfb09e5addbdf3c71a0725137c7bba3340ef8e597",
    "output/ocr_state_paddleocr-vl.json": "60f16801464cf96063f1cb07aafd044e5ec68fff69e35e6696a5abb8f76ec6c1",
    "output/katex_dots-mocr.json": "8cad66c56eb9e589f76ab33d6559ac6584aa03bde3821309af3b090bbcfb4a8d",
    "output/katex_paddleocr-vl.json": "19fdd1e704b7864cfad3ac605c75088d407951d28c7c191d9cb2cfe538a02d1d",
    "output/recall_dots-mocr.json": "8203fb88c5f117bb9925d32fafbc3d3456d44b9bd95e963d8df7570f24ef4e5a",
    "output/recall_paddleocr-vl.json": "5e2ad24929151a97e051c887b39bd3ac451e3b7c971b793fbf8ee33c2159d49f",
    "output/dots-mocr": "888575e61e7a4351d18628ebff48bdcd73a842410347dd2b151073f53b6aac4f",
    "output/paddleocr-vl": "9c0aebfc69c2576a52e41a79a1d9fe0ff782d9b436ab08dd483dea960af3f462",
    f"{EXP33_REL}/build_labels.py": "4d9faa5437ee02d3de256a0fea156f9b02942e1798e2784a4f022497ac1ba2fa",
    f"{EXP33_REL}/output/local_ocr/pages.json": "e6223d1536293b6860cd8eda9d48b2e383139e3e6c2f5e095a36f2b9822a711f",
    f"{EXP33_REL}/output/.transcripts": "ed9e0e184ef59dc6184d3f981cc9cc08ad221e199f062d6a59213bf47d8e3453",
    "make_noise_review.py": "2f76388212152229f238ca2a7adaa514e8675b179641ea3c8a6139053c8fbb5e",
    f"{EXP34_REL}/make_review.py": "e0ae1c377440335262b2209f509749dfbd163674a56f698b5aa57687b3de8622",
    f"{EXP34_REL}/extra_pages.py": "7212aa9fd9d0b8a13e7df0a0633be304a2e86d0db51bbc69187fceeaa184ad85",
    f"{EXP33_REL}/output/.transcripts_split": "2cc5f067a5df45247cfb627c67f640508a04c82c836c05bac2e76296b35b3e44",
}
DISPLAY = re.compile(r"\$\$([\s\S]*?)\$\$")
INLINE = re.compile(r"(?<![\\$])\$([^$\n]+?)\$(?!\$)")  # check_katex.mjs extract(), same rule


def check_pinned(names: Iterable[str]) -> dict[str, str]:
    """Return the SHA-256 of each named input; stop when one is missing or changed (OI-7)."""
    found: dict[str, str] = {}
    for name in names:
        path = run_ocr.EXP37 / name
        if path.is_dir():
            lines = (
                f"{p.relative_to(path).as_posix()}\0{run_ocr.sha256_file(p)}\n"
                for p in sorted(path.rglob("*"))
                if p.is_file()
            )
            digest = hashlib.sha256("".join(lines).encode()).hexdigest()
        elif path.is_file():
            digest = run_ocr.sha256_file(path)
        else:
            raise SystemExit(f"input is missing: {path}")
        if digest != PINNED[name]:
            raise SystemExit(f"{name} changed: expected {PINNED[name]}, found {digest}")
        found[name] = digest
    return found


def exp33_tokens() -> Any:
    """Import ``build_labels.tokens`` from the Experiment 33 folder of this worktree."""
    path = EXP33 / "build_labels.py"
    if run_ocr.sha256_file(path) != BUILD_LABELS_SHA256:
        raise SystemExit(
            "Experiment 33 build_labels.py changed: the tokeniser is not the frozen one"
        )
    spec = importlib.util.spec_from_file_location("exp33_build_labels", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.tokens


def dice(a: list[str], b: list[str]) -> float:
    """Return the multiset Dice coefficient of two token lists (1.0 when both are empty)."""
    if not a and not b:
        return 1.0
    return 2 * sum((Counter(a) & Counter(b)).values()) / (len(a) + len(b))


def formulas(text: str) -> Counter[str]:
    """Return the formulas of *text*, whitespace removed (display first, then inline)."""
    found = [re.sub(r"\s+", "", body) for body in DISPLAY.findall(text)]
    found += [re.sub(r"\s+", "", body) for body in INLINE.findall(DISPLAY.sub(" ", text))]
    return Counter(found)


def compare(arm: str, baseline: str) -> dict[str, Any]:
    """Score *arm* against *baseline* on the frozen page lists; return the result."""
    inputs = check_pinned(
        ["output/" + run_ocr.BASELINES[b] for b in (arm, baseline) if b in run_ocr.BASELINES]
    )
    tokens = exp33_tokens()
    keys = list(run_ocr.select_pages(run_ocr.page_lists(run_ocr.load_plan()), "all"))
    scores: dict[str, float] = {}
    lost: dict[str, dict[str, list[str]]] = {}
    skipped = {"arm_missing": 0, "baseline_missing": 0}
    base_formulas = missing = added = 0
    for key in keys:
        base_file, arm_file = run_ocr.page_path(baseline, key), run_ocr.page_path(arm, key)
        if not base_file.is_file():
            skipped["baseline_missing"] += 1
        elif not arm_file.is_file():
            skipped["arm_missing"] += 1
        else:
            base_text, arm_text = base_file.read_text("utf-8"), arm_file.read_text("utf-8")
            scores[key] = round(dice(tokens(arm_text), tokens(base_text)), 4)
            have, want = formulas(arm_text), formulas(base_text)
            gone, extra = want - have, have - want
            base_formulas += sum(want.values())
            missing, added = missing + sum(gone.values()), added + sum(extra.values())
            if gone or extra:
                lost[key] = {
                    "missing": list(gone.elements()),
                    "added": list(extra.elements()),
                }
    values = list(scores.values())
    ranked = sorted(scores.items(), key=lambda item: (item[1], item[0]))
    return {
        "arm": arm,
        "baseline": baseline,
        "tokeniser": "experiments/33-ocr-routing-natural-positive-2026-09-17/build_labels.py tokens()",
        "inputs_sha256": inputs,
        "pages_compared": len(values),
        **skipped,
        "dice": {
            "median": round(statistics.median(values), 4) if values else None,
            "mean": round(statistics.fmean(values), 4) if values else None,
            "share_below_0_9": round(sum(v < 0.9 for v in values) / len(values), 4)
            if values
            else None,
        },
        "lowest_20": [{"page": k, "dice": v} for k, v in ranked[:20]],
        "formulas": {
            "baseline_total": base_formulas,
            "missing_from_arm": missing,
            "added_by_arm": added,
            "pages_with_difference": lost,
        },
        "pages": scores,
    }


def review_list(
    dice_by_page: dict[str, float],
    flagged: Iterable[str],
    *,
    lowest: int = 10,
    random_pages: int = 5,
    seed: int = SEED,
) -> dict[str, list[str]]:
    """Select the pages the operator reviews (DR-3); return ``{page: reasons}``.

    The pages are the *lowest* pages by Dice, every page the noise screen *flagged*, and
    *random_pages* more drawn with *seed* from the pages not yet chosen.
    """
    chosen: dict[str, list[str]] = {}
    for key in sorted(dice_by_page, key=lambda k: (dice_by_page[k], k))[:lowest]:
        chosen.setdefault(key, []).append("lowest_similarity")
    for key in sorted(set(flagged)):
        chosen.setdefault(key, []).append("noise_screen")
    rest = sorted(set(dice_by_page) - chosen.keys())
    for key in random.Random(seed).sample(rest, min(random_pages, len(rest))):  # noqa: S311 - seeded sample
        chosen.setdefault(key, []).append("random")
    return chosen


# ── Review pages (task 6.2) ───────────────────────────────────────────────

REVIEW_ARMS = ("D4", "D2", "P4", "P2")
VERDICTS = ("clean", "invented")  # the values summarise.py reads
RENDER_SCALE = 1.5  # the Experiment 37 page-image scale
KATEX_DIR = "../tools/katex/node_modules/katex/dist"  # relative to output/; no CDN
CSS = (
    "<style>.form .note{font:inherit;font-size:.82rem;padding:.3rem .5rem;border:1px solid var(--line);"
    "border-radius:6px;background:var(--card);color:var(--ink)}mark{background:#ffe08a;color:inherit}"
    "@media (prefers-color-scheme:dark){mark{background:#6b5200}}.role{margin-left:.2rem}"
    "#progress{font-size:.95rem;font-weight:700;color:var(--ink);background:var(--soft);"
    "border:1px solid var(--line);border-radius:999px;padding:.25rem .8rem}"
    "#progress.ok{color:#fff;background:var(--ok);border-color:var(--ok)}</style>\n"
)
JS = """
const pages=[...document.querySelectorAll('details.page')];
const slots=[...document.querySelectorAll('fieldset.form[data-slot]')];
const STORE='exp41-review-'+ARM;
function collect(){const o={};for(const f of slots){const r=f.querySelector('input:checked');if(r)o[f.dataset.slot]={verdict:r.value,note:f.querySelector('.note').value}}return o}
function refresh(){let done=0,pdone=0;
 for(const p of pages){const f=p.querySelector('fieldset.form');const on=!!f.querySelector('input:checked');if(on){done++;pdone++}
  const s=p.querySelector('.pstat');s.textContent=on?'\\u2713 '+f.querySelector('input:checked').value:'needs verdict';s.className='pstat'+(on?' ok':'');p.dataset.done=on?'1':''}
 const pr=document.getElementById('progress');pr.textContent='Done '+done+' / '+slots.length+' verdicts \\u00b7 '+pdone+' / '+pages.length+' pages';pr.className=done===slots.length?'ok':'';
 try{localStorage.setItem(STORE,JSON.stringify(collect()))}catch(e){pr.textContent+=' \\u00b7 autosave unavailable: download often'}}
try{const by=JSON.parse(localStorage.getItem(STORE)||'{}');for(const f of slots){const v=by[f.dataset.slot];if(!v)continue;const r=f.querySelector('input[value='+v.verdict+']');if(r)r.checked=true;f.querySelector('.note').value=v.note||''}}catch(e){}
document.addEventListener('change',refresh);document.addEventListener('input',refresh);
document.addEventListener('click',e=>{const c=e.target.closest('.clear');if(c){const f=c.closest('.form');f.querySelectorAll('input').forEach(i=>{i.checked=false;if(i.classList.contains('note'))i.value=''});refresh();return}
 const v=e.target.closest('.vt');if(v){const w=v.closest('.outwrap');w.querySelectorAll('.vt').forEach(b=>b.classList.toggle('on',b===v));w.querySelector('.md').hidden=v.dataset.v!=='md';w.querySelector('.raw').hidden=v.dataset.v!=='raw'}});
for(const p of pages)p.addEventListener('toggle',()=>{if(!p.open)return;let moved=false;for(const o of pages)if(o!==p&&o.open){if(o.compareDocumentPosition(p)&Node.DOCUMENT_POSITION_FOLLOWING)moved=true;o.open=false}if(moved)p.scrollIntoView({block:'start'});
 p.querySelectorAll('details.engine').forEach(d=>d.open=true)});
document.getElementById('next').onclick=()=>{const p=pages.find(x=>!x.dataset.done);if(!p)return alert('All pages reviewed.');p.open=true;p.scrollIntoView({behavior:'smooth',block:'start'})};
document.getElementById('collapse').onclick=()=>pages.forEach(p=>p.open=false);
document.getElementById('dl').onclick=()=>{const v=collect(),left=slots.length-Object.keys(v).length;if(left)return alert(left+' pages still need a verdict. The export stays blocked until every page has one.');
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({verdicts:{[ARM]:v}},null,1)],{type:'application/json'}));a.download='review_verdicts_'+ARM+'_download.json';a.click()};
refresh();
"""


def load_noise_module() -> Any:
    """Import Experiment 37 ``make_noise_review.py`` by path after a SHA-256 check."""
    check_pinned(
        ["make_noise_review.py", f"{EXP34_REL}/make_review.py", f"{EXP34_REL}/extra_pages.py"]
    )
    check_pinned([f"{EXP33_REL}/build_labels.py", f"{EXP33_REL}/output/.transcripts"])
    spec = importlib.util.spec_from_file_location(
        "exp37_noise_review", run_ocr.EXP37 / "make_noise_review.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def reference_text(noise: Any, run: str, pdf: Path, key: str) -> str:
    """Return the DR-4 reference: PDF text layer (E-maths) or Experiment 33 transcription."""
    doc, page = key.split(":")
    if run == "E-maths":
        return noise.reference_text(run, pdf, doc, int(page))
    path = run_ocr.EXP37.parent / EXP33_REL.removeprefix("../") / "output/.transcripts"
    record = json.loads((path / doc / f"p{int(page):03d}.json").read_text("utf-8"))
    return record.get("transcription") or ""


def noise_screen(noise: Any, tokens: Any, text: str, reference: str) -> dict[str, Any]:
    """Apply the DR-4 rule to one page: unsupported tokens, repeated lines, flag."""
    ref = Counter(tokens(reference))
    have = Counter(tokens(noise.prose(text)))
    unsupported = Counter({t: n - ref[t] for t, n in have.items() if n > ref[t]})
    total, n_un = sum(have.values()), sum(unsupported.values())
    loops = noise.repeated_lines(text)
    share = n_un / total if total else 0.0
    return {
        "tokens": total,
        "unsupported": n_un,
        "share": round(share, 4),
        "repeated_lines": loops,
        "flagged": (n_un >= noise.MIN_UNSUPPORTED and share >= noise.MIN_SHARE) or bool(loops),
        "unsupported_sample": [t for t, _ in unsupported.most_common(40)],
    }


def render_images(keys: list[str]) -> None:
    """Render the page images that do not exist yet to ``output/review_pages`` (pypdfium2)."""
    import pypdfium2

    target = run_ocr.OUT / "review_pages"
    missing = [
        k
        for k in keys
        if not (target / k.split(":")[0] / f"p{int(k.split(':')[1]):03d}.png").is_file()
    ]
    for doc, path in run_ocr.corpus(missing).items():
        pdf = pypdfium2.PdfDocument(str(path))
        for key in (k for k in missing if k.startswith(doc + ":")):
            out = target / doc / f"p{int(key.split(':')[1]):03d}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(out.name + ".tmp")
            pdf[int(key.split(":")[1]) - 1].render(scale=RENDER_SCALE).to_pil().save(
                tmp, format="PNG"
            )
            tmp.replace(out)
        pdf.close()


def card(noise: Any, key: str, run: str, item: dict[str, Any], text: str) -> str:
    """One page in the Experiment 34 layout: image pinned left, the arm's output right."""
    doc, page = key.split(":")
    image = f"review_pages/{doc}/p{int(page):03d}.png"
    screen = item.get("screen")
    roles = "".join(
        f'<span class="role badge">{r.replace("_", " ")}</span>' for r in item["reasons"]
    )
    note = (
        f"{screen['unsupported']} of {screen['tokens']} tokens not in the reference ({screen['share']:.0%})"
        if screen
        else "no reference screen (E-script)"
    )
    loops = (
        f'<div class="pending">Repeated lines: {html.escape("; ".join(screen["repeated_lines"]))}</div>'
        if screen and screen["repeated_lines"]
        else ""
    )
    raw = noise.highlight(text, set(screen["unsupported_sample"]) if screen else set())
    chips = "".join(
        f'<label class="chip"><input type="radio" name="{key}" value="{v}"><span>{v}</span></label>'
        for v in VERDICTS
    )
    return f"""
<details class="page" data-key="{key}">
  <summary><span class="pt">{key} · {run} · Dice {item["dice"]}</span>{roles}<span class="pstat"></span></summary>
  <div class="body">
    <div class="orig"><div class="stick">
      <button type="button" class="zoom" data-src="{image}" data-cap="{key}" aria-label="Open zoomable view">
        <img loading="lazy" src="{image}" alt="{key}"><span class="mag" aria-hidden="true">⌕</span>
      </button>
      <div class="hint">Click to zoom · pinch or ⌘/Ctrl-scroll inside the viewer</div>
    </div></div>
    <div class="right"><details class="engine"><summary><span class="en">{item["arm"]}</span><span class="badge">{note}</span></summary>
      <fieldset class="form" data-slot="{key}"><div class="q"><div class="ql">Does the output contain text that is not on the page image?</div>
      <div class="opts">{chips}</div></div><input class="note" placeholder="note (optional)"><button type="button" class="clear">Clear</button></fieldset>{loops}
      <div class="outwrap"><div class="viewbar"><button type="button" class="vt on" data-v="md">Rendered</button>
      <button type="button" class="vt" data-v="raw">Raw + highlights</button></div>
      <div class="md">{noise.render_markdown(text)}</div><pre class="raw" hidden>{raw}</pre></div></details></div>
  </div>
</details>"""


def page_html(noise: Any, arm: str, cards: str, empty: dict[str, str], baseline: str) -> str:
    """Return the review page of *arm*: Experiment 34 style and viewer, local KaTeX."""
    style, viewer, zoom_js = noise._exp34_parts()
    delimiters = "[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]"
    none = "; ".join(f"{k} ({v})" for k, v in sorted(empty.items())) or "none"
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Experiment 41 review {arm}</title>\n"
        f'<link rel="stylesheet" href="{KATEX_DIR}/katex.min.css">\n'
        f'<script defer src="{KATEX_DIR}/katex.min.js"></script>\n'
        f'<script defer src="{KATEX_DIR}/contrib/auto-render.min.js" onload="renderMathInElement('
        f"document.body,{{delimiters:{delimiters},ignoredClasses:['raw'],throwOnError:false}})\"></script>\n"
        f"{style}\n{CSS}</head><body>\n"
        f'<div class="bar"><strong>Experiment 41 review: {arm} (gate C5)</strong> <span id="progress"></span>'
        ' <button id="next" type="button">Next unreviewed</button>'
        ' <button id="collapse" type="button">Collapse all</button>'
        ' <button id="dl" type="button">Download verdicts</button></div>\n<main>\n'
        f'<p class="intro">Judge the text of {arm} against the page image. '
        "<b>invented</b>: the output holds text that is not on the page (made up, garbage or bleed-through). "
        "<b>clean</b>: every piece of text is on the page. The image stays pinned on the left; click it to zoom. "
        "Rendered shows Markdown and maths (KaTeX 0.16.22, local) with layout tags removed and every word kept. "
        "Raw + highlights shows the exact text; highlighted words are not in the reference text (hint only). "
        f"The badges give why a page is listed (DR-3). Baseline for Dice: {baseline}. "
        "The download holds this arm only and stays blocked until every page has a verdict.</p>\n"
        f'<p class="intro">Not reviewed (no text): {html.escape(none)}.</p>\n'
        f"{cards}\n</main>\n{viewer}<script>(() => {{const ARM={json.dumps(arm)};{JS}\n{zoom_js}}})();</script></body></html>\n"
    )


def review_arm(arm: str, noise: Any) -> dict[str, Any]:
    """Screen *arm*, select its review pages (DR-3), write its HTML page; return the record."""
    tokens = exp33_tokens()
    engine = run_ocr.ARMS[arm][0]
    baseline = {v: k for k, v in run_ocr.BASELINES.items()}[engine]
    sim = json.loads((run_ocr.OUT / f"similarity_{arm}_vs_{baseline}.json").read_text("utf-8"))
    state = json.loads(run_ocr.state_path(arm).read_text("utf-8"))["pages"]
    runs = run_ocr.select_pages(run_ocr.page_lists(run_ocr.load_plan()), "all")
    texts: dict[str, str] = {}
    empty: dict[str, str] = {}
    for key in runs:
        path = run_ocr.page_path(arm, key)
        text = path.read_text("utf-8") if path.is_file() else ""
        if text.strip():
            texts[key] = text
        else:
            status = str(state.get(key, {}).get("status", "missing"))
            empty[key] = "blank text, status ok" if status == "ok" else status
    screened = [k for k in texts if runs[k] in noise.RUNS]
    pdfs = run_ocr.corpus(screened)
    screens = {
        k: noise_screen(
            noise, tokens, texts[k], reference_text(noise, runs[k], pdfs[k.split(":")[0]], k)
        )
        for k in screened
    }
    dice = {k: v for k, v in sim["pages"].items() if k in texts}
    chosen = review_list(dice, [k for k, s in screens.items() if s["flagged"]])
    items = {
        k: {"arm": arm, "reasons": r, "dice": dice[k], "screen": screens.get(k)}
        for k, r in sorted(chosen.items())
    }
    render_images(list(items))
    cards = "".join(card(noise, k, runs[k], items[k], texts[k]) for k in items)
    run_ocr.write_atomic(
        run_ocr.OUT / f"review_{arm}.html", page_html(noise, arm, cards, empty, baseline)
    )
    reasons = Counter(r for v in items.values() for r in v["reasons"])
    return {
        "baseline": baseline,
        "rule": "DR-3: 10 lowest Dice, every noise-screen flag, 5 random (seed 41); DR-4 screen",
        "pages_with_text": len(texts),
        "pages_without_text": empty,
        "flagged_by_screen": sorted(k for k, s in screens.items() if s["flagged"]),
        "reason_counts": dict(reasons),
        "review_pages": len(items),
        "pages": {
            k: {"reasons": v["reasons"], "run": runs[k], "dice": v["dice"]}
            for k, v in items.items()
        },
    }


def review(arms: Iterable[str]) -> int:
    """Build the review page of each arm; merge the records into ``review_selection.json``."""
    noise = load_noise_module()
    target = run_ocr.OUT / "review_selection.json"
    record = json.loads(target.read_text("utf-8")) if target.is_file() else {}
    for arm in arms:
        record[arm] = review_arm(arm, noise)
        print(f"{arm}: {record[arm]['review_pages']} pages {record[arm]['reason_counts']}")
    run_ocr.write_atomic(target, json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    return 0


def main() -> int:
    """Write the similarity file for one arm, or build the review pages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=sorted(run_ocr.ARMS) + sorted(run_ocr.BASELINES))
    parser.add_argument("--baseline", choices=sorted(run_ocr.ARMS) + sorted(run_ocr.BASELINES))
    parser.add_argument(
        "--review", action="store_true", help="build the review pages (all arms, or --arm)"
    )
    args = parser.parse_args()
    if args.review:
        return review([args.arm] if args.arm else REVIEW_ARMS)
    if not args.arm:
        parser.error("--arm is required without --review")
    engine = run_ocr.BASELINES.get(args.arm) or run_ocr.ARMS[args.arm][0]
    baseline = args.baseline or {v: k for k, v in run_ocr.BASELINES.items()}[engine]
    result = compare(args.arm, baseline)
    target = run_ocr.OUT / f"similarity_{args.arm}_vs_{baseline}.json"
    run_ocr.write_atomic(target, json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(f"{args.arm} vs {baseline}: {result['pages_compared']} pages, Dice {result['dice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
