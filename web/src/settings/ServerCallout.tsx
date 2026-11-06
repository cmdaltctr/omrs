import { Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

const TONES = {
  info: "rounded-small border border-status-info bg-status-info/10 px-3 py-2 text-ui text-status-info-label",
  warning: "rounded-small border border-status-warning bg-status-warning/10 px-3 py-2 text-ui text-status-warning-label",
} as const;

const ICONS = { info: Info, warning: TriangleAlert } as const;

/** Fixed words, such as the facts of the router mode or a note with a link: `info` for a fact, `warning` for a risk. */
export function ServerCallout({ text, tone = "info" }: { text: ReactNode; tone?: keyof typeof TONES }) {
  const Icon = ICONS[tone];
  return (
    <div role="note" className={`flex min-w-0 gap-2 ${TONES[tone]}`}>
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0 [overflow-wrap:anywhere]">{text}</p>
    </div>
  );
}
