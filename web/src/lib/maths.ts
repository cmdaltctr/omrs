/**
 * The one maths configuration. Every surface that renders LaTeX takes its
 * plugin lists from here, so the KaTeX options cannot drift between surfaces.
 */
import type { Options } from "react-markdown";
import rehypeKatex, { type Options as RehypeKatexOptions } from "rehype-katex";
import remarkMath from "remark-math";

/**
 * `trust` is the KaTeX default. It is set on purpose, so a later edit has to
 * remove it deliberately: with it off, `\href`, `\url`, `\includegraphics` and
 * the `\html*` commands render as plain command names and add no element.
 * `maxSize` (in em) bounds a `\rule` or a box, which KaTeX leaves unlimited.
 * `rehype-katex` renders a formula that fails to parse as a `span.katex-error`
 * that holds its LaTeX source, in `errorColor`. It never throws into React.
 */
export const KATEX_OPTIONS: RehypeKatexOptions = {
  trust: false,
  maxSize: 20,
  errorColor: "var(--status-error-label)",
};

/** The part of an mdast node that the plugins below read. */
export interface MdNode {
  type: string;
  value?: string;
  position?: { start: { offset?: number }; end: { offset?: number } };
  data?: { hName: string; hChildren: { type: string; value: string }[] };
  children?: MdNode[];
}

/**
 * A text node that reaches the page exactly as written. `mdast-util-to-hast`
 * trims the spaces around every line break of a plain text node, so the text
 * goes through a `span` instead, which it leaves alone.
 */
export function exactText(value: string): MdNode {
  return { type: "text", value, data: { hName: "span", hChildren: [{ type: "text", value }] } };
}

/**
 * Whether the source text of an `inlineMath` node is a real formula. A single
 * `$` pair opens maths only when no space follows the opening dollar sign, no
 * space comes before the closing one, and no digit follows it (the rule that
 * pandoc uses). This keeps "It costs $5 and $10" and `echo $HOME and $PATH`
 * as text. A `$$ ... $$` pair on one line is always maths.
 */
function isRealInlineMath(source: string): boolean {
  if (!source.startsWith("$") || source.startsWith("$$")) return true;
  const closed = source.endsWith("$");
  const content = source.slice(1, closed ? -1 : undefined);
  return content !== "" && !/^\s|\s$/.test(content);
}

/** Replaces each `inlineMath` node that is not a real formula with the text it was parsed from. */
function remarkRejectLooseDollars() {
  return (root: unknown, file: { value?: unknown }) => {
    const tree = root as MdNode;
    const source = String(file.value ?? "");
    const walk = (node: MdNode) => {
      node.children?.forEach((child, index) => {
        if (child.type === "inlineMath") {
          const start = child.position?.start.offset;
          const end = child.position?.end.offset;
          if (start === undefined || end === undefined) return;
          const raw = source.slice(start, end);
          const next = source[end];
          if (isRealInlineMath(raw) && !(raw.startsWith("$") && !raw.startsWith("$$") && next !== undefined && /\d/.test(next))) return;
          node.children![index] = { ...exactText(raw), position: child.position };
          return;
        }
        walk(child);
      });
    };
    walk(tree);
  };
}

/** `remark-math` with its defaults (`dots-mocr` writes inline maths as `$...$`), then the dollar rule above. */
export const remarkMathPlugins: NonNullable<Options["remarkPlugins"]> = [remarkMath, remarkRejectLooseDollars];

export const rehypeMathPlugins: NonNullable<Options["rehypePlugins"]> = [[rehypeKatex, KATEX_OPTIONS]];
