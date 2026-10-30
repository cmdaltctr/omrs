import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { connectionsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { ClientConfiguration, McpHttpPanel } from "./McpHttpPanel";

/** The configuration a stdio client needs: it starts `omrs` in the folder whose `.env` the server read. */
export function stdioConfiguration(configDir: string): string {
  return JSON.stringify({ mcpServers: { omrs: { command: "uv", args: ["run", "--directory", configDir, "omrs"] } } }, null, 2);
}

function StdioPanel() {
  const query = useQuery(connectionsQuery(useApi()));
  const configDir = query.data?.config_dir;
  return (
    <Card role="region" aria-labelledby="mcp-stdio-title" className="@container">
      <CardHeader>
        <CardTitle id="mcp-stdio-title">Stdio client</CardTitle>
        <p className="text-meta text-muted-foreground">The client starts its own omrs process, so no server needs to run.</p>
      </CardHeader>
      {configDir === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <div data-slot="mcp-columns" className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 @3xl:grid-cols-2">
          <p className="text-ui">
            Starts omrs with{" "}
            <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
              {`uv run --directory ${configDir} omrs`}
            </code>
            , so it reads the same .env as this server.
          </p>
          <ClientConfiguration text={stdioConfiguration(configDir)} what="stdio configuration" />
        </div>
      )}
    </Card>
  );
}

/** How to connect an MCP client: over stdio, or over HTTP to this server. Each way is one full-width card. */
export function McpSection() {
  return (
    <section aria-labelledby="settings-mcp" className="flex flex-col gap-3">
      <h2 id="settings-mcp" className="text-section-title font-semibold">
        MCP
      </h2>
      <StdioPanel />
      <McpHttpPanel />
    </section>
  );
}
