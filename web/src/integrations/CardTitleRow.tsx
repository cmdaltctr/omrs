import type { ReactNode } from "react";
import { CardTitle } from "../components/ui/card";

/**
 * A card's title with its badges. The badges keep the top-right corner and a
 * long title wraps beside them, so badges never drop to a row of their own.
 */
export function CardTitleRow({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div data-slot="card-title-row" className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
      <CardTitle className="min-w-0 [overflow-wrap:anywhere]">{title}</CardTitle>
      <div className="flex flex-wrap items-center justify-end gap-1.5">{children}</div>
    </div>
  );
}
