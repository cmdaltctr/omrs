import type { IntegrationList } from "../api/integrations";
import { MasonryColumns } from "../components/MasonryColumns";
import { availabilityNote } from "./ExtrasSection";
import { SectionFrame } from "./SectionFrame";
import { ToolCard } from "./ToolCard";
import type { InstallControl } from "./useIntegrationInstall";

/** External tools. Each goes into its own uv tool environment, apart from the server's extras (ADR-101). */
export function ToolsSection({ list, control }: { list: IntegrationList; control: InstallControl }) {
  return (
    <SectionFrame
      id="integrations-tools"
      title="Tools"
      lines={["Programs that run beside OMRS, each in its own uv tool environment.", availabilityNote(list)]}
    >
      <div role="list" aria-label="External tools">
        <MasonryColumns>
          {list.tools.map((tool) => (
            <div key={tool.id} role="listitem" className="min-w-0">
              <ToolCard tool={tool} control={control} />
            </div>
          ))}
        </MasonryColumns>
      </div>
    </SectionFrame>
  );
}
