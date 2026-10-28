import type { IntegrationList } from "../api/integrations";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { attentionCount, SECTION_LABELS, type IntegrationSection } from "./sections";

interface SectionChipsProps {
  sections: IntegrationSection[];
  current: IntegrationSection;
  list: IntegrationList | undefined;
  onSelect: (next: IntegrationSection) => void;
}

/** The chip row, as in Settings. A runtime section that holds red parts shows how many on its chip. */
export function SectionChips({ sections, current, list, onSelect }: SectionChipsProps) {
  return (
    <div role="group" aria-label="Sections" className="flex flex-wrap gap-2">
      {sections.map((section) => {
        const label = SECTION_LABELS[section];
        const count = attentionCount(section, list);
        return (
          <Button
            key={section}
            variant="chip"
            aria-pressed={current === section}
            aria-label={count > 0 ? `${label}, ${count} needs attention` : label}
            onClick={() => onSelect(section)}
          >
            {label}
            {count > 0 ? (
              <Badge variant="error" aria-hidden="true" className="tabular-nums">
                {count}
              </Badge>
            ) : null}
          </Button>
        );
      })}
    </div>
  );
}
