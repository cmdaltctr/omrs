import { useState } from "react";
import type { Connection, ProviderField, ProviderGroup } from "../api/settings";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { isLoopback, ROLE_NAMES } from "./connectionWords";
import { ModelDownloadPanel } from "./ModelDownloadPanel";
import { IntegrationLink } from "./IntegrationLink";
import { ProviderFieldGroups } from "./ProviderFieldGroups";
import { DenseSettingRows } from "./SettingBox";
import { ProviderTest } from "./ProviderTest";

interface ProviderCardProps {
  connection: Connection;
  keychain: "available" | "unavailable";
  /** The folder whose `.env` the server read. */
  configDir: string;
  /** Full row width: from 768 px of card width the card splits into two columns. */
  wide?: boolean;
}

/** The parts of a wide card, by column: the addresses and models left, Chat and its server right. */
const LEFT_PARTS = [null, "embeddings", "metadata"] as const;
const RIGHT_PARTS = ["answers"] as const;

/** The address a field would use if the user saved the typed text now. */
function addressInUse(field: ProviderField, typed: Record<string, string>): string | null {
  return field.kind === "url" ? (typed[field.id] ?? String(field.value ?? "")) : null;
}

/**
 * One provider: badges, roles, editable fields and read-only values (in blocks on
 * the llama.cpp card), notices and a Test action. A wide card puts its blocks in
 * two columns: addresses and models left, Chat and Get a model right.
 */
export function ProviderCard({ connection, keychain, configDir, wide = false }: ProviderCardProps) {
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

  const fields = (parts?: readonly (ProviderGroup | null)[]) => (
    <ProviderFieldGroups connection={connection} keychain={keychain} configDir={configDir} onTyped={setValue} parts={parts} />
  );
  const notInstalled = connection.installed ? null : (
    <p className="text-ui">
      {"Not installed. "}
      <IntegrationLink connection={connection} />
      {"."}
    </p>
  );
  const download =
    connection.model_source != null ? (
      <div data-slot="model-download" className="min-w-0">
        <ModelDownloadPanel provider={connection.provider} source={connection.model_source} />
      </div>
    ) : null;
  // The card's own notice and Test sit at its foot, outside the setting rows.
  const foot = (
    <div className="mt-auto flex flex-col gap-3">
      {offMachine ? (
        <p className="text-meta text-muted-foreground">
          {connection.locality === "cloud" ? "Text you send to this provider leaves this machine." : "This address is not on this machine, so text sent to it leaves this machine."}
        </p>
      ) : null}
      <ProviderTest provider={connection.provider} typed={typed} cloud={connection.locality === "cloud"} />
    </div>
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

  // Settings rows are compact on this page, so a card with many settings stays short.
  return (
    <Card role="region" aria-labelledby={titleId} className={wide ? "@container" : undefined}>
      {header}
      <DenseSettingRows>
        {wide ? (
          <div data-slot="provider-columns" className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-3 @3xl:grid-cols-2">
            <div className="flex min-w-0 flex-col gap-3">
              {notInstalled}
              {fields(LEFT_PARTS)}
            </div>
            <div className="flex min-w-0 flex-col gap-3">
              {fields(RIGHT_PARTS)}
              {download}
            </div>
          </div>
        ) : (
          <>
            {notInstalled}
            {fields()}
            {download}
          </>
        )}
      </DenseSettingRows>
      {foot}
    </Card>
  );
}
