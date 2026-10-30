import type { IntegrationList } from "../api/integrations";
import { IntegrationCard } from "./IntegrationCard";
import { EntryList } from "./EntryList";
import { SectionFrame } from "./SectionFrame";
import type { InstallControl } from "./useIntegrationInstall";

/** True when the server can install an entry from this page. */
function canInstall(list: IntegrationList): boolean {
  if (list.integrations.some((integration) => integration.installable)) return true;
  return (
    list.install_type === "uv-tool" &&
    !list.integrations.some((integration) => integration.install_reason === "uv-not-found")
  );
}

/** The note under the Extras heading: what availability means and how an install takes effect. */
function availabilityNote(list: IntegrationList): string {
  const lead = "Availability reflects the running launch of the server.";
  return canInstall(list)
    ? `${lead} Install adds the packages to the server. A restart makes them available.`
    : `${lead} This server cannot install extras from the app. To add an extra, run its command in a terminal outside the app, then restart the server.`;
}

/** Python package extras, one row each in server order, in one card. */
export function ExtrasSection({ list, control }: { list: IntegrationList; control: InstallControl }) {
  return (
    <SectionFrame
      id="integrations-extras"
      title="Extras"
      lines={["Python package extras that add backends, readers and providers to the server.", availabilityNote(list)]}
    >
      <EntryList label="Integrations">
        {list.integrations.map((integration) => (
          <IntegrationCard key={integration.id} integration={integration} installType={list.install_type} control={control} />
        ))}
      </EntryList>
    </SectionFrame>
  );
}
