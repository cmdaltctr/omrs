"""Markdown rendering for the Experiment 35 labelling page (rendered in Python, no script).

Answers and passages are Markdown, and FreshStack text holds much code. The
renderer keeps fenced code as monospaced blocks, inline code as code, and
renders headings, lists, paragraphs and pipe tables. Bold, italic, links (text
only) and citation markers render in every text field. Every character of the
data is HTML-escaped first, so no HTML from the data runs. ``$`` stays literal:
there is no maths rendering, because FinanceBench text is full of amounts.

Experiment 34's ``_mini_markdown`` is not reused: it has no lists, no inline
code and no fence language, and its italic rule would eat ``*`` inside code.
"""

from __future__ import annotations

import html
import re

#: Placeholders around the marked sentence; replaced after escaping and rendering.
MARK_OPEN, MARK_CLOSE = "\x01", "\x02"
_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\([^)\s]*\)")
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
#: Bold opens before a non-space that is not closing punctuation (CommonMark flanking, simplified).
_BOLD = re.compile(r"\*\*(?=[^\s,;.:!?)])(.+?)(?<=[^\s(])\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?=[^*\s])(.+?)(?<=[^*\s])\*(?![*\w])")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^\s*(\d{1,9})[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")
#: Between two claim characters the answer may hold spaces and citation markers.
_GAP = r"(?:\s|\[[0-9,\s]*\])*"
_LIST_LEAD = re.compile(r"^(?:[-*+]|\d{1,9}[.)])\s+")
#: A YAML front matter block at the start of a passage (FreshStack documents).
_FRONT = re.compile(r"^---\n(.*?)\n---[ \t]*\n?", re.S)
_SOURCE_EXT = re.compile(r"source_url:\s*\"?[^\"\n]*\.(\w+)\"?")
_PROSE_EXT = {"md", "mdx", "markdown", "rst", "txt"}
#: Lines that look like source code: an indent of four spaces or a tab, a leading keyword
#: or comment, or a code-like ending.
_CODE_LEAD = re.compile(
    r"^(?: {4}|\t)|^\s*(import |from \S+ import|def |class |return\b|const |let |var |export |async |"
    r"await |@\w|//|/\*|\*/|#!|\}|\{|print\()"
)
_CODE_END = tuple("{}();,[=:")
#: Share of non-blank lines that must look like code. Checked on smoke passages (first six
#: run files per dataset): 0 of 108 BioASQ and FinanceBench passages reach 0.3; 20 of 24
#: FreshStack passages without front matter reach 0.5.
CODE_SHARE = 0.5


def _marks(text: str) -> str:
    return text.replace(MARK_OPEN, '<mark class="target">').replace(MARK_CLOSE, "</mark>")


def _prose(text: str) -> str:
    out = html.escape(text, quote=False)
    out = _LINK.sub(r"\1", out)
    out = _CITE.sub(r'<span class="cite">[\1]</span>', out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    # Unpaired bold markers (a claim cut out of a bold span) carry no meaning: drop them.
    return _ITALIC.sub(r"<em>\1</em>", out).replace("**", "")


def render_inline(text: str) -> str:
    """Return one line of Markdown as escaped HTML with inline formatting.

    Inline code is swapped for placeholders first, so bold or italic around a
    code span still pairs up and ``*`` inside code is never formatting.
    """
    codes: list[str] = []

    def hold(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
        return f"\x03{len(codes) - 1}\x04"

    out = _prose(_CODE.sub(hold, text))
    out = re.sub("\x03(\\d+)\x04", lambda m: codes[int(m.group(1))], out)
    return _marks(out)


def _table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head = len(rows) > 1 and _SEPARATOR.match(rows[1].strip()) is not None
    body: list[str] = []
    for n, row in enumerate(cells):
        if head and n == 1:
            continue
        tag = "th" if head and n == 0 else "td"
        body.append("<tr>" + "".join(f"<{tag}>{render_inline(c)}</{tag}>" for c in row) + "</tr>")
    return '<div class="tbl"><table>' + "".join(body) + "</table></div>"


def _take(lines: list[str], i: int, pattern: re.Pattern[str]) -> tuple[list[re.Match[str]], int]:
    found: list[re.Match[str]] = []
    while i < len(lines) and (match := pattern.match(lines[i])):
        found.append(match)
        i += 1
    return found, i


def render_markdown(text: str) -> str:
    """Return Markdown as escaped HTML: fences, headings, lists, tables and paragraphs."""
    lines = (text or "").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            marker, lang = fence.group(1), fence.group(2)
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                code.append(lines[i])
                i += 1
            attr = f' data-lang="{lang}"' if lang else ""
            body = html.escape("\n".join(code), quote=False)
            out.append(f'<pre class="code"{attr}><code>{_marks(body)}</code></pre>')
            i += 1
        elif not line.strip():
            i += 1
        elif _RULE.match(line):
            out.append("<hr>")
            i += 1
        elif heading := _HEADING.match(line.strip()):
            tag = f"h{min(len(heading.group(1)) + 2, 6)}"
            out.append(f"<{tag}>{render_inline(heading.group(2))}</{tag}>")
            i += 1
        elif line.strip().startswith("|"):
            start = i
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            out.append(_table(lines[start:i]))
        elif _BULLET.match(line):
            items, i = _take(lines, i, _BULLET)
            out.append("<ul>" + "".join(f"<li>{render_inline(m.group(1))}</li>" for m in items))
            out.append("</ul>")
        elif _NUMBER.match(line):
            items, i = _take(lines, i, _NUMBER)
            first = int(items[0].group(1))
            start_attr = f' start="{first}"' if first != 1 else ""
            out.append(f"<ol{start_attr}>")
            out.append("".join(f"<li>{render_inline(m.group(2))}</li>" for m in items) + "</ol>")
        else:
            out.append(f"<p>{render_inline(line)}</p>")
            i += 1
    return "".join(out)


def mark_claim(answer: str, claim: str) -> str:
    """Return *answer* with the claim's span wrapped in mark placeholders.

    A claim is the answer sentence with citation markers removed and spaces
    tidied (``split_claims``), so the span is found by matching the claim's
    characters with optional spaces and markers between them. A leading list
    marker stays outside the mark. When the claim is not found, the answer
    comes back unchanged.
    """
    core = "".join(_LIST_LEAD.sub("", claim.strip()).split())
    if not core:
        return answer
    found = re.search(_GAP.join(re.escape(ch) for ch in core), answer)
    if found is None:
        return answer
    start, end = found.span()
    return answer[:start] + MARK_OPEN + answer[start:end] + MARK_CLOSE + answer[end:]


def _code_block(text: str, lang: str = "", extra: str = "") -> str:
    attr = f' data-lang="{lang}"' if lang else ""
    body = html.escape(text.strip("\n"), quote=False)
    return f'<pre class="code{extra}"{attr}><code>{body}</code></pre>'


def looks_like_code(text: str) -> bool:
    """Return True when most non-blank lines of *text* look like source code."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    hits = sum(bool(_CODE_LEAD.match(x)) or x.rstrip().endswith(_CODE_END) for x in lines)
    return hits / len(lines) >= CODE_SHARE


def render_passage(text: str) -> str:
    """Return one passage as HTML: source code as a code block, else Markdown.

    A front matter block shows as a small code block. Its ``source_url``
    extension decides the body: a document extension renders as Markdown, any
    other as code. Without front matter, a passage with no fence whose lines
    mostly look like code renders as one code block.
    """
    front = _FRONT.match(text)
    if front is None:
        if "```" not in text and looks_like_code(text):
            return _code_block(text)
        return render_markdown(text)
    body = text[front.end() :]
    ext = _SOURCE_EXT.search(front.group(1))
    lang = ext.group(1).lower() if ext else ""
    meta = _code_block(front.group(1), extra=" meta")
    if lang in _PROSE_EXT or (not lang and not looks_like_code(body)):
        return meta + render_markdown(body)
    return meta + _code_block(body, lang)
