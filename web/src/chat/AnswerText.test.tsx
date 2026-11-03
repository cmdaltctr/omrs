import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Citation, Evidence } from "../api/documents";
import { TooltipProvider } from "../components/ui/tooltip";
import { EQ01_CHUNKS } from "../test/eq01Fixture";
import { AnswerText, ClaimList } from "./AnswerText";

function cite(ordinal: number): Citation {
  return {
    ordinal, chunk_id: `c-${ordinal}`, chunk_ids: [`c-${ordinal}`], source_id: "sid-1", source_version: "v7",
    source: "/srv/docs/paper.pdf", source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1",
  } as Citation;
}

function show(text: string, citations: Citation[] = [cite(1), cite(2)]) {
  const evidence = citations.map((c) => ({ ...c, text: `Evidence ${c.ordinal}` })) as Evidence[];
  return render(
    <TooltipProvider>
      <AnswerText text={text} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
    </TooltipProvider>,
  );
}

describe("AnswerText markdown", () => {
  it("renders **bold** and *italic* as elements, with no asterisks left", () => {
    const { container } = show("This is **strong** and *soft* text.");
    expect(container.querySelector("strong")).toHaveTextContent("strong");
    expect(container.querySelector("em")).toHaveTextContent("soft");
    expect(container).not.toHaveTextContent("*");
  });

  it("renders headings at their own level", () => {
    show("# Title\n\n## Section\n\n### Part\n\nBody");
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Section" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Part" })).toBeInTheDocument();
  });

  it("renders unordered and ordered lists with one item per entry", () => {
    show("- alpha\n- beta\n\n1. first\n2. second\n3. third");
    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(within(lists[0]!).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["alpha", "beta"]);
    expect(lists[1]!.tagName).toBe("OL");
    expect(within(lists[1]!).getAllByRole("listitem")).toHaveLength(3);
  });

  it("renders inline code and a fenced code block with its language and exact text", () => {
    const { container } = show("Use `top_k` here.\n\n```python\nx = 1\nprint(x)\n```");
    expect(screen.getByText("top_k").tagName).toBe("CODE");
    const block = container.querySelector("pre code");
    expect(block).not.toBeNull();
    expect(block!.textContent).toBe("x = 1\nprint(x)\n");
    expect(block).toHaveClass("language-python");
  });

  it("renders a GFM table", () => {
    show("| a | b |\n| - | - |\n| 1 | 2 |");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "a" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2" })).toBeInTheDocument();
  });

  it("does not render raw HTML or script from the model", () => {
    const { container } = show('Hi <b>raw</b><script>window.__x = 1</script><img src="x" onerror="1">');
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders a link as a safe external anchor and drops a javascript: href", () => {
    show("[docs](https://example.com/a) and [bad](javascript:alert(1))");
    const good = screen.getByRole("link", { name: "docs" });
    expect(good).toHaveAttribute("href", "https://example.com/a");
    expect(good).toHaveAttribute("target", "_blank");
    expect(good).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.queryByRole("link", { name: "bad" })).toBeNull();
  });
});

describe("AnswerText maths", () => {
  it.each(EQ01_CHUNKS.map((chunk) => [chunk.chunk_id.slice(0, 8), chunk] as const))(
    "renders every formula of eq01 chunk %s as maths with no KaTeX error",
    (_id, chunk) => {
      const { container } = show(chunk.text);
      expect(container.querySelectorAll(".katex-error")).toHaveLength(0);
      expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(chunk.formulas);
    },
  );

  it("renders inline and display maths as KaTeX", () => {
    const { container } = show("Inline $x^2$ here.\n\n$$\n\\sum_i y_i\n$$");
    expect(container.querySelectorAll(".katex")).toHaveLength(2);
    expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(container).not.toHaveTextContent("$");
  });

  it("shows a formula that cannot be parsed as its source in the error element and keeps the text after it", () => {
    const { container } = show("Before $\\frac{a}{$ after");
    const errors = container.querySelectorAll(".katex-error");
    expect(errors).toHaveLength(1);
    expect(errors[0]).toHaveTextContent("\\frac{a}{");
    expect(container).toHaveTextContent("after");
  });

  it("renders a formula next to HTML and creates no element from the HTML, which shows as text", () => {
    const { container } = show("$x$ <b>raw</b><script>window.__x = 1</script>");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container).toHaveTextContent("<b>raw</b>");
  });

  it("renders a merged passage whose closing fence is followed by prose and inline maths", () => {
    const { container } = show("as:\n\n$$\n\\log p = a\n$$\nwhere again the term $y_i$ holds");
    expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(container.querySelectorAll(".katex-error")).toHaveLength(0);
    expect(container).toHaveTextContent("where again the term");
  });

  it("shows dollar amounts as text, with every space", () => {
    const { container } = show("It costs $5 and $10, or $40 more. A ton of coal is another $");
    expect(container.querySelector(".katex")).toBeNull();
    expect(container).toHaveTextContent("It costs $5 and $10, or $40 more. A ton of coal is another $");
  });

  it("creates no link from a \\href command in a formula", () => {
    const { container } = show("$\\href{javascript:alert(1)}{x}$");
    // With trust off KaTeX shows the command name in the error colour and drops its argument.
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector(".katex-html")).toHaveTextContent("\\href");
    expect(container.querySelector("a")).toBeNull();
  });

  it("creates no element from HTML inside a formula", () => {
    const { container } = show("$<script>$");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector("script")).toBeNull();
  });

  it("keeps [1] after a formula as a citation button", () => {
    const { container } = show("The bound $\\mathcal{L}(\\theta, \\phi; \\mathbf{x})$ holds [1]");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
  });

  it("does not make a citation button from [1] inside a formula", () => {
    show("The term $a_{[1]}$ is local.");
    expect(screen.queryByRole("button", { name: "Citation 1" })).toBeNull();
  });
});

describe("AnswerText citations inside markdown", () => {
  it("keeps [n] as a citation button inside bold, a list item and a heading", () => {
    show("## Result [1]\n\n- item **strong [2]**");
    expect(screen.getByRole("heading", { level: 2 })).toContainElement(screen.getByRole("button", { name: "Citation 1" }));
    expect(screen.getByRole("listitem")).toContainElement(screen.getByRole("button", { name: "Citation 2" }));
    expect(screen.getByRole("button", { name: "Citation 2" }).closest("strong")).not.toBeNull();
  });

  it("leaves a marker with no matching citation as text", () => {
    show("Known [1] and unknown [7].");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText(/unknown \[7\]/)).toBeInTheDocument();
  });

  it("turns each ordinal of a grouped marker [1, 3] into its own citation button", () => {
    const { container } = show("Shown in two papers [1, 3, 7].", [cite(1), cite(2), cite(3)]);
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Citation 3" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(container).toHaveTextContent("papers [1, 3, 7].");
  });

  it("does not turn [n] inside inline code or a code block into a button", () => {
    show("Index `a[1]` here.\n\n```\nb[2]\n```");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("a[1]")).toBeInTheDocument();
  });
});

describe("ClaimList", () => {
  function claims(items: { claim: string; verdict: string; ordinals: number[] }[]) {
    const citations = [cite(1), cite(2)];
    const evidence = citations.map((c) => ({ ...c, text: `Evidence ${c.ordinal}` })) as Evidence[];
    return render(
      <TooltipProvider>
        <ClaimList claims={items} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
      </TooltipProvider>,
    );
  }

  it("renders inline code in a claim as code, with no backticks left", () => {
    const { container } = claims([{ claim: "Run `omrs --version` first.", verdict: "unsupported", ordinals: [1] }]);
    expect(screen.getByText("omrs --version").tagName).toBe("CODE");
    expect(container).not.toHaveTextContent("`");
  });

  it("renders inline maths in a claim, with no dollar signs left", () => {
    const { container } = claims([{ claim: "The prior is $p_{\\theta}(\\mathbf{z})$", verdict: "unsupported", ordinals: [1] }]);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    // The inner KaTeX spans and the MathML survive the claim filter, so the formula is not unwrapped.
    expect(container.querySelector(".katex .katex-html")).not.toBeNull();
    expect(container.querySelector(".katex math")).not.toBeNull();
    expect(container).not.toHaveTextContent("$");
  });

  it("shows a display formula in a claim as an inline formula, since a claim keeps inline maths only", () => {
    const { container } = claims([{ claim: "$$\nx^2\n$$", verdict: "unsupported", ordinals: [1] }]);
    expect(container.querySelector(".katex-display")).toBeNull();
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
  });

  it("drops a heading in a claim to text and still renders its formula", () => {
    const { container } = claims([{ claim: "# Heading $x$", verdict: "unsupported", ordinals: [1] }]);
    expect(container.querySelector("h1")).toBeNull();
    expect(container).toHaveTextContent("Heading");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
  });

  it("renders the cited ordinal of a claim as a citation button", () => {
    claims([{ claim: "A claim.", verdict: "unsupported", ordinals: [1, 2] }]);
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Citation 2" })).toBeInTheDocument();
    expect(screen.getByText(/unsupported/)).toBeInTheDocument();
  });

  it("keeps a marker with no matching citation as text", () => {
    claims([{ claim: "A claim.", verdict: "unsupported", ordinals: [9] }]);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/cites \[9\]/)).toBeInTheDocument();
  });

  it("shows a claim that is only a code fence as written", () => {
    const { container } = claims([{ claim: "```", verdict: "unsupported", ordinals: [1] }]);
    expect(container.querySelector("pre")).toBeNull();
    expect(container).toHaveTextContent("```");
  });

  it("keeps one list item per claim and the list label", () => {
    claims([
      { claim: "One.", verdict: "unsupported", ordinals: [1] },
      { claim: "Two.", verdict: "contradicted", ordinals: [2] },
    ]);
    const list = screen.getByRole("list", { name: "Claims that failed verification" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("AnswerText spacing", () => {
  const SAMPLE = "## Steps\n\nFirst paragraph.\n\nSecond paragraph.\n\n1. one\n2. two\n   - nested a\n   - nested b\n\n- alpha\n- beta\n\nLast paragraph.";

  it("puts every top-level block in one spaced column", () => {
    const { container } = show(SAMPLE);
    const column = container.firstElementChild as HTMLElement;
    expect(column).toHaveClass("flex", "flex-col", "gap-4");
    const tags = Array.from(column.children).map((el) => el.tagName);
    expect(tags).toEqual(["H2", "P", "P", "OL", "UL", "P"]);
  });

  it("spaces list items from each other", () => {
    const { container } = show(SAMPLE);
    for (const list of container.querySelectorAll("ul, ol")) expect(list).toHaveClass("flex", "flex-col", "gap-2");
  });

  it("spaces a nested list and a second paragraph from the text above them in an item", () => {
    const { container } = show("1. item text\n   - nested\n\n2. second\n\n   continued paragraph");
    for (const item of container.querySelectorAll("li")) expect(item).toHaveClass("[&>*+*]:mt-2");
  });

  it("separates a heading from the paragraph that follows it", () => {
    const { container } = show("### Title\n\nBody text.");
    const column = container.firstElementChild as HTMLElement;
    expect(column.children[0]!.tagName).toBe("H3");
    expect(column.children[1]!.tagName).toBe("P");
    expect(column).toHaveClass("gap-4");
  });
});

describe("citation buttons and copied text", () => {
  it("lets the reader select a citation in the answer, so a copy keeps the number", () => {
    show("A claim [1].");
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("select-text");
  });

  it("lets the reader select a citation in a failed claim", () => {
    const citations = [cite(1)];
    const evidence = citations.map((c) => ({ ...c, text: "Evidence 1" })) as Evidence[];
    render(
      <TooltipProvider>
        <ClaimList claims={[{ claim: "A claim.", verdict: "unsupported", ordinals: [1] }]} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("select-text");
  });

  it("keeps a citation close to the punctuation after it", () => {
    show("A claim [1].");
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("px-0");
  });
});

describe("AnswerText list items", () => {
  const LOOSE = "- first item [1]\n\n- second item\n\n1. one\n\n2. two";

  it("does not keep the newline text between an item's children, so the bullet shares a line with its text", () => {
    const { container } = show(LOOSE);
    for (const item of container.querySelectorAll("li")) {
      // A loose item holds a newline text node before its paragraph. With pre-line it renders as a line break.
      expect(item).not.toHaveClass("whitespace-pre-line");
      expect(item.firstElementChild?.tagName).toBe("P");
    }
  });

  it("colours the bullet and number markers with the primary label colour", () => {
    const { container } = show(LOOSE);
    for (const list of container.querySelectorAll("ul, ol")) expect(list).toHaveClass("marker:text-primary-label");
  });
});
