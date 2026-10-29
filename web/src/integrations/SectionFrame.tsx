import type { ReactNode } from "react";

/** The heading and summary lines of one Integrations section, over its content. */
export function SectionFrame({
  id,
  title,
  lines,
  children,
}: {
  id: string;
  title: string;
  lines: string[];
  children: ReactNode;
}) {
  return (
    <section role="region" aria-labelledby={id} className="flex flex-col gap-3">
      <div>
        <h2 id={id} className="text-section-title font-semibold">
          {title}
        </h2>
        {lines.map((line, index) => (
          // The last line of Extras and Tools is the availability note.
          <p key={line} role={index > 0 ? "note" : undefined} className="text-meta text-muted-foreground">
            {line}
          </p>
        ))}
      </div>
      {children}
    </section>
  );
}
