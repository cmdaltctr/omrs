import type { IntegrationList } from "../api/integrations";
import { EntryList } from "./EntryList";
import { SectionFrame } from "./SectionFrame";
import { ToolCard } from "./ToolCard";
import type { InstallControl } from "./useIntegrationInstall";

/** External tools. Each goes into its own uv tool environment, apart from the server's extras (ADR-101). */
export function ToolsSection({ list, control }: { list: IntegrationList; control: InstallControl }) {
  return (
    <SectionFrame
      id="integrations-tools"
      title="Tools"
      lines={[
        "Programs that run beside OMRS, each in its own uv tool environment.",
        "A tool installs into its own environment, so the server needs no restart. Each card says what to do next.",
      ]}
    >
      <EntryList label="External tools">
        {list.tools.map((tool) => (
          <ToolCard key={tool.id} tool={tool} control={control} />
        ))}
      </EntryList>
    </SectionFrame>
  );
}
