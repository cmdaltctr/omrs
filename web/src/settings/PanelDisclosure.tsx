import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

interface PanelDisclosureProps {
  /** The id of the title, which names the panel. */
  titleId: string;
  title: string;
  /** The heading level of the title inside the card. */
  level: 4 | 5;
  /** One short line of state beside the title, such as "Stopped". */
  summary?: string | null;
  /** Opens the panel while true, for example when its server failed. */
  attention?: boolean;
  children: ReactNode;
}

/**
 * A panel of a provider card that starts closed, with its title and a state
 * line on the toggle row. The content stays mounted while closed, so a running
 * download or a typed value is kept.
 */
export function PanelDisclosure({ titleId, title, level, summary = null, attention = false, children }: PanelDisclosureProps) {
  const [open, setOpen] = useState(false);
  const Heading = level === 4 ? "h4" : "h5";

  return (
    <details
      aria-labelledby={titleId}
      open={open || attention}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="group min-w-0 rounded-control border border-border"
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-control px-3 py-2 transition-colors duration-150 hover:bg-interactive-hover [&::-webkit-details-marker]:hidden">
        <Heading id={titleId} className="text-ui font-semibold">
          {title}
        </Heading>
        <span className="min-w-0 flex-1 truncate text-meta text-muted-foreground">{summary}</span>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0 transition-transform duration-150 group-open:rotate-180" />
      </summary>
      <div className="flex min-w-0 flex-col gap-2 border-t border-border px-3 py-3">{children}</div>
    </details>
  );
}
