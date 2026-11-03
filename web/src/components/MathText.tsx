import Markdown from "react-markdown";
import type { Plugin } from "unified";
import { exactText, rehypeMathPlugins, remarkMathPlugins, type MdNode } from "../lib/maths";

const isMath = (node: MdNode) => node.type === "math" || node.type === "inlineMath";

/** Every maths node of the tree, in source order, with its offsets. */
function mathNodes(node: MdNode, found: MdNode[] = []): MdNode[] {
  for (const child of node.children ?? []) {
    if (isMath(child)) found.push(child);
    else mathNodes(child, found);
  }
  return found;
}

/**
 * Keeps only the maths of the parsed tree. Chunk text is raw OCR or source
 * text, so every other character must stay as written: the plugin cuts the
 * source between the maths nodes into plain text nodes and drops the rest of
 * the Markdown tree. A display formula owns the line breaks that touch its
 * `$$` fences, because the block is a line of its own.
 */
const remarkMathOnly: Plugin<[]> = function remarkMathOnly() {
  return (root: unknown, file: { value?: unknown }) => {
    const tree = root as MdNode;
    const source = String(file.value ?? "");
    const children: MdNode[] = [];
    let cursor = 0;
    const text = (from: number, to: number) => {
      if (to > from) children.push(exactText(source.slice(from, to)));
    };
    for (const node of mathNodes(tree).sort((a, b) => a.position!.start.offset! - b.position!.start.offset!)) {
      const start = node.position!.start.offset!;
      const end = node.position!.end.offset!;
      const block = node.type === "math";
      text(cursor, block && source[start - 1] === "\n" ? start - 1 : start);
      children.push(node);
      cursor = block && source[end] === "\n" ? end + 1 : end;
    }
    text(cursor, source.length);
    tree.children = children;
  };
};

interface MathTextProps {
  text: string;
}

/**
 * Chunk text with `$...$` and `$$...$$` rendered as maths and every other
 * character shown as written, with its indentation and line breaks kept. It is
 * parsed into React elements and never into raw HTML.
 */
export function MathText({ text }: MathTextProps) {
  return (
    <div className="min-w-0 whitespace-pre-wrap break-words">
      <Markdown remarkPlugins={[...remarkMathPlugins, remarkMathOnly]} rehypePlugins={rehypeMathPlugins}>
        {text}
      </Markdown>
    </div>
  );
}
