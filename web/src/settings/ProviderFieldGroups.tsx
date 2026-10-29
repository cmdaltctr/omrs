import type { Connection, ProviderField, ProviderGroup, ReadOnlyValue } from "../api/settings";
import { CardInset } from "../components/ui/card";
import { PROVIDER_EXTRAS } from "./providerExtras";
import { ProviderKeyField } from "./ProviderKeyField";
import { ProviderValueField } from "./ProviderValueField";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

/** The blocks of a provider card, in the order they show. */
const GROUPS: { id: ProviderGroup; title: string }[] = [
  { id: "embeddings", title: "Embeddings" },
  { id: "metadata", title: "Classification (metadata)" },
  { id: "answers", title: "Chat" },
];

interface ProviderFieldGroupsProps {
  connection: Connection;
  keychain: "available" | "unavailable";
  /** The folder whose `.env` the server read. */
  configDir: string;
  /** Called with the text typed in a field, or `null` when its input closes. The card uses it for Test. */
  onTyped: (id: string, text: string | null) => void;
}

/** The line under a field that uses another field's value while no source sets it. */
function followLine(field: ProviderField, fields: ProviderField[]): string | null {
  if (field.follows === null || field.source !== "default") return null;
  const followed = fields.find((other) => other.id === field.follows);
  return followed === undefined ? null : `Uses the ${followed.label} until you set one.`;
}

function ReadOnlyValues({ values }: { values: ReadOnlyValue[] }) {
  return (
    <CardInset>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-ui">
        {values.map((entry) => (
          <div key={entry.label} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-meta text-muted-foreground">
              {entry.label} <span>(Read-only)</span>
            </dt>
            <dd>
              <code dir="ltr" className={CODE}>
                {entry.value}
              </code>
            </dd>
          </div>
        ))}
      </dl>
    </CardInset>
  );
}

/**
 * The fields and read-only values of a provider card. Values with no group
 * come first, then each block (Embeddings, Classification (metadata), Chat)
 * under its title, with the provider's extra panels for that block at its end.
 * A card whose values have no group shows no block titles.
 */
export function ProviderFieldGroups({ connection, keychain, configDir, onTyped }: ProviderFieldGroupsProps) {
  const extras = PROVIDER_EXTRAS[connection.provider] ?? [];

  const part = (group: ProviderGroup | null) => {
    const fields = connection.fields.filter((field) => field.group === group);
    const values = connection.read_only.filter((entry) => entry.group === group);
    const panels = extras.filter((extra) => extra.group === group);
    if (fields.length === 0 && values.length === 0 && panels.length === 0) return null;
    return (
      <>
        {fields.map((field) =>
          field.kind === "secret" ? (
            <ProviderKeyField key={field.id} provider={connection.provider} field={field} keychain={keychain} onTyped={(text) => onTyped(field.id, text === "" ? null : text)} />
          ) : (
            <ProviderValueField key={field.id} provider={connection.provider} field={field} configDir={configDir} note={followLine(field, connection.fields)} onTyped={(text) => onTyped(field.id, text)} />
          ),
        )}
        {values.length > 0 ? <ReadOnlyValues values={values} /> : null}
        {panels.map(({ Component }, index) => (
          <div key={index} data-slot="provider-extra" className="flex min-w-0 flex-col gap-3">
            <Component />
          </div>
        ))}
      </>
    );
  };

  return (
    <>
      {part(null)}
      {GROUPS.map(({ id, title }) => {
        const body = part(id);
        if (body === null) return null;
        const headingId = `provider-${connection.provider}-${id}`;
        return (
          <div key={id} role="group" aria-labelledby={headingId} className="flex min-w-0 flex-col gap-3 border-t border-border pt-3">
            <h4 id={headingId} className="text-ui font-semibold">
              {title}
            </h4>
            {body}
          </div>
        );
      })}
    </>
  );
}
