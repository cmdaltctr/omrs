import { createContext, useContext, type ComponentProps, type ReactNode } from "react";
import { CardInset } from "../components/ui/card";
import { cn } from "../lib/utils";

const DenseContext = createContext(false);

/**
 * Inside it, setting rows drop their mini card and show as compact rows with
 * a hairline between them. Providers, Document reading, MCP and the
 * Appearance Text card use it, because their cards hold many settings each;
 * the other Settings tabs keep mini cards.
 */
export function DenseSettingRows({ children }: { children: ReactNode }) {
  return <DenseContext.Provider value={true}>{children}</DenseContext.Provider>;
}

/** True inside `DenseSettingRows`. */
export function useDenseRows(): boolean {
  return useContext(DenseContext);
}

/** One setting: a mini card, or a compact row inside `DenseSettingRows`. */
export function SettingBox({ className, ...props }: ComponentProps<"div">) {
  const dense = useDenseRows();
  if (!dense) return <CardInset className={className} {...props} />;
  return <div data-slot="setting-row" className={cn("flex min-w-0 flex-col gap-1.5 border-b border-border py-2 last:border-b-0", className)} {...props} />;
}
