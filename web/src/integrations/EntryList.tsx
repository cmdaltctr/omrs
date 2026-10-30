import type { ReactNode } from "react";
import { Card } from "../components/ui/card";
import { CardTitleRow } from "./CardTitleRow";

/**
 * One section's entries as rows in a single full-width card, as on the
 * Settings pages. Rows keep server order and a hairline between them, so a
 * tall row never leaves a gap beside a short one.
 */
export function EntryList({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card className="@container gap-0 py-1">
      <div role="list" aria-label={label} className="flex min-w-0 flex-col">
        {children}
      </div>
    </Card>
  );
}

interface EntryRowProps {
  /** The DOM id, so a link such as `#/integrations/anthropic` can focus the row. */
  id?: string;
  title: string;
  badges: ReactNode;
  /** What the entry is for, under the title. */
  purpose: string;
  /** State lines under the purpose: readiness, version, reason. */
  details?: ReactNode;
  /** Install and uninstall controls and the commands. From 768 px of card width they sit in the right column. */
  actions?: ReactNode;
}

/** One entry: name, badges and purpose on the left, actions and commands on the right. */
export function EntryRow({ id, title, badges, purpose, details, actions }: EntryRowProps) {
  return (
    <div
      id={id}
      tabIndex={id === undefined ? undefined : -1}
      role="listitem"
      data-slot="entry-row"
      className="grid min-w-0 scroll-mt-4 grid-cols-1 gap-x-6 gap-y-3 border-b border-border py-4 last:border-b-0 @3xl:grid-cols-2"
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <CardTitleRow title={title}>{badges}</CardTitleRow>
        <p className="text-meta text-muted-foreground">{purpose}</p>
        {details}
      </div>
      {actions === undefined ? null : <div className="flex min-w-0 flex-col gap-3">{actions}</div>}
    </div>
  );
}
