import { useState } from "react";
import type { Connection, ProviderField } from "../api/settings";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { isLoopback, ROLE_NAMES } from "./connectionWords";
import { ModelDownloadPanel } from "./ModelDownloadPanel";
import { IntegrationLink } from "./IntegrationLink";
import { ProviderFieldGroups } from "./ProviderFieldGroups";
import { ProviderTest } from "./ProviderTest";

interface ProviderCardProps {
  connection: Connection;
  keychain: "available" | "unavailable";
  /** The folder whose `.env` the server read. */
  configDir: string;
}

/** The address a field would use if the user saved the typed text now. */
function addressInUse(field: ProviderField, typed: Record<string, string>): string | null {
  return field.kind === "url" ? (typed[field.id] ?? String(field.value ?? "")) : null;
}

/** One provider: badges, roles, editable fields and read-only values (in blocks on the llama.cpp card), notices and a Test action. */
export function ProviderCard({ connection, keychain, configDir }: ProviderCardProps) {
  const titleId = `provider-${connection.provider}`;
  const [typed, setTyped] = useState<Record<string, string>>({});
  const setValue = (id: string, value: string | null) =>
    setTyped((current) => {
      const next = { ...current };
      if (value === null) delete next[id];
      else next[id] = value;
      return next;
    });
  const offMachine =
    connection.locality === "cloud" || connection.fields.some((field) => {
      const address = addressInUse(field, typed);
      return address !== null && address !== "" && !isLoopback(address);
    });

  const body = (
    <>
      {!connection.installed ? (
        <p className="text-ui">
          {"Not installed. "}
          <IntegrationLink connection={connection} />
          {"."}
        </p>
      ) : null}
      <ProviderFieldGroups connection={connection} keychain={keychain} configDir={configDir} onTyped={setValue} />
      {offMachine ? (
        <p className="text-meta text-muted-foreground">
          {connection.locality === "cloud" ? "Text you send to this provider leaves this machine." : "This address is not on this machine, so text sent to it leaves this machine."}
        </p>
      ) : null}
      <ProviderTest provider={connection.provider} typed={typed} cloud={connection.locality === "cloud"} />
    </>
  );

  const header = (
    <CardHeader>
      <CardTitle id={titleId}>{connection.display_name}</CardTitle>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={connection.locality === "cloud" ? "warning" : "success"}>{connection.locality === "cloud" ? "Cloud" : "Local"}</Badge>
        {connection.roles.length > 0 ? (
          connection.roles.map((role) => (
            <Badge key={role} variant="hue">
              {ROLE_NAMES[role]}
            </Badge>
          ))
        ) : (
          <span className="text-meta text-muted-foreground">No role uses this provider.</span>
        )}
      </div>
    </CardHeader>
  );

  // A card with extra panels stays in one column and grows taller, with each
  // panel in its block. The masonry columns absorb the height.
  return (
    <Card role="region" aria-labelledby={titleId}>
      {header}
      {body}
      {connection.model_source != null && (
        <div data-slot="model-download" className="min-w-0 border-t border-border pt-3">
          <ModelDownloadPanel provider={connection.provider} source={connection.model_source} />
        </div>
      )}
    </Card>
  );
}
