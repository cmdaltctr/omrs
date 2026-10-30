import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

/** A multi-line field with the same tokens as `Input`. `mono` sets monospace text for files and code. */
function Textarea({ className, mono = false, rows = 20, ...props }: ComponentProps<"textarea"> & { mono?: boolean }) {
  return (
    <textarea
      data-slot="textarea"
      rows={rows}
      className={cn(
        "flex w-full min-w-0 resize-y rounded-control border border-border bg-card px-2.5 py-2 text-ui text-foreground transition-colors duration-150 selection:bg-selection placeholder:text-muted-foreground hover:border-border-hover focus-visible:border-ring focus-visible:shadow-[inset_0_0_0_1px_var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-destructive",
        mono && "font-mono text-code",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
