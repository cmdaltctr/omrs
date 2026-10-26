import { useId, type ReactNode } from "react";
import { Card } from "../components/ui/card";

interface PanelProps {
  title: string;
  /** One sentence under the title. */
  description?: string;
  /** Heading level; the view heading is the `h1`. */
  level?: 2 | 3;
  /** Controls at the end of the title row, such as an Edit button. */
  actions?: ReactNode;
  children: ReactNode;
}

/** A named card: its heading names the region for assistive technology. */
export function Panel({ title, description, level = 2, actions, children }: PanelProps) {
  const id = useId();
  const Heading = level === 2 ? "h2" : "h3";
  const header = (
    <div className="flex min-w-0 flex-col gap-1">
      <Heading id={id} className={level === 2 ? "text-section-title font-semibold" : "text-subsection-title font-semibold"}>
        {title}
      </Heading>
      {description !== undefined ? <p className="text-meta text-muted-foreground">{description}</p> : null}
    </div>
  );
  return (
    <section aria-labelledby={id}>
      <Card>
        {actions === undefined ? (
          header
        ) : (
          <div className="flex flex-wrap items-start justify-between gap-2">
            {header}
            <div className="flex flex-wrap items-center gap-2">{actions}</div>
          </div>
        )}
        {children}
      </Card>
    </section>
  );
}
