import { useMemo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";

export type LinkTarget = { kind: "file"; name: string } | { kind: "external"; href: string } | { kind: "text" };

const EXTERNAL = /^(?:https?:|mailto:)/i;

/**
 * Where a Markdown link leads. A web or mail link opens in a new tab. A
 * relative link to a top-level file of the same experiment (`./protocol.md`,
 * `report.md#method`) opens that file in the page. Anything else, such as a
 * bare `#anchor` or a path into another folder, stays text: as a link it
 * would change the app's address.
 */
export function resolveLink(href: string, fileNames: ReadonlySet<string>): LinkTarget {
  if (EXTERNAL.test(href)) return { kind: "external", href };
  let path = href.split("#")[0]!.split("?")[0]!.replace(/^\.\//, "");
  try {
    path = decodeURIComponent(path);
  } catch {
    return { kind: "text" };
  }
  return path !== "" && !path.includes("/") && fileNames.has(path) ? { kind: "file", name: path } : { kind: "text" };
}

const HEADING = "mt-2 font-semibold text-foreground";

// The page owns the h1 and the panel owns the h2, so Markdown headings start at h3.
const BASE: Components = {
  h1: ({ children }) => <h3 className={`${HEADING} text-section-title`}>{children}</h3>,
  h2: ({ children }) => <h4 className={`${HEADING} text-subsection-title`}>{children}</h4>,
  h3: ({ children }) => <h5 className={`${HEADING} text-ui`}>{children}</h5>,
  h4: ({ children }) => <h6 className={`${HEADING} text-ui`}>{children}</h6>,
  h5: ({ children }) => <h6 className={`${HEADING} text-ui`}>{children}</h6>,
  h6: ({ children }) => <h6 className={`${HEADING} text-ui`}>{children}</h6>,
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="flex list-disc flex-col gap-1 ps-5 marker:text-primary-label">{children}</ul>,
  ol: ({ start, children }) => (
    <ol start={start} className="flex list-decimal flex-col gap-1 ps-5 marker:text-primary-label">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-relaxed [&>*+*]:mt-1">{children}</li>,
  blockquote: ({ children }) => <blockquote className="border-s-2 border-border ps-3 text-muted-foreground">{children}</blockquote>,
  hr: () => <hr className="border-border" />,
  code: ({ className, children }) => <code className={`rounded-small bg-muted px-1 font-mono text-code ${className ?? ""}`}>{children}</code>,
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-control border border-border bg-muted p-3 font-mono text-code [&>code]:bg-transparent [&>code]:p-0">{children}</pre>
  ),
  table: ({ children }) => <Table>{children}</Table>,
  thead: ({ children }) => <TableHeader>{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow>{children}</TableRow>,
  th: ({ children }) => <TableHead>{children}</TableHead>,
  td: ({ children }) => <TableCell>{children}</TableCell>,
  // An image would load from an address the file chooses. Show its text instead.
  img: ({ alt }) => <span className="text-muted-foreground">{alt ? `[Image: ${alt}]` : "[Image]"}</span>,
};

interface MarkdownTextProps {
  text: string;
  /** The top-level file names of the experiment, for relative links. */
  fileNames: ReadonlySet<string>;
  onOpenFile: (name: string) => void;
}

/**
 * Markdown from an experiment file (GitHub flavour). It is parsed into React
 * elements and never into raw HTML, so markup such as `<script>` in the file
 * shows as text.
 */
export function MarkdownText({ text, fileNames, onOpenFile }: MarkdownTextProps) {
  const components = useMemo<Components>(
    () => ({
      ...BASE,
      a: ({ href, children }) => {
        const target = href ? resolveLink(href, fileNames) : ({ kind: "text" } as const);
        if (target.kind === "external") {
          return (
            <a href={target.href} target="_blank" rel="noopener noreferrer" className="text-primary-label underline underline-offset-4 hover:no-underline">
              {children}
            </a>
          );
        }
        if (target.kind === "file") {
          return (
            <Button variant="link" size="inline" className="whitespace-normal px-0 text-start align-baseline underline" onClick={() => onOpenFile(target.name)}>
              {children}
            </Button>
          );
        }
        return <span className="underline decoration-dotted underline-offset-4">{children}</span>;
      },
    }),
    [fileNames, onOpenFile],
  );
  return (
    <div className="flex min-w-0 flex-col gap-3 break-words text-ui">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </Markdown>
    </div>
  );
}
