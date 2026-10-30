import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { mcpQuery } from "../api/queries";
import { useSetMcpEnabled } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { isEnvironmentSource, sourceText } from "./connectionWords";
import { CopyButton } from "./CopyButton";
import { McpTokenPanel } from "./McpTokenPanel";
import { DenseSettingRows, SettingBox } from "./SettingBox";
import { WebPortPanel } from "./WebPortPanel";
import { SaveErrorNotice } from "./SaveErrorNotice";

/** The configuration of an HTTP client. The token placeholder is replaced by the token shown once. */
export function httpConfiguration(url: string): string {
  const config = { mcpServers: { omrs: { type: "http", url, headers: { Authorization: "Bearer omrs_mcp_<token>" } } } };
  return JSON.stringify(config, null, 2);
}

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const META = "text-meta text-muted-foreground";

/** A client configuration with its Copy button, the right column of an MCP card. */
export function ClientConfiguration({ text, what }: { text: string; what: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h4 className="text-ui font-semibold">Client configuration</h4>
      <pre dir="ltr" tabIndex={0} className="overflow-x-auto rounded-control border border-border bg-muted p-3 text-code font-mono">
        {text}
      </pre>
      <div>
        <CopyButton text={text} what={what} />
      </div>
    </div>
  );
}

/**
 * The MCP-over-HTTP card. Left: the switch and address as compact rows, then
 * the token and the web port. Right: the client configuration. The columns
 * split from 768 px of card width.
 */
export function McpHttpPanel() {
  const query = useQuery(mcpQuery(useApi()));
  const change = useSetMcpEnabled();
  const state = query.data;

  return (
    <Card role="region" aria-labelledby="mcp-http-title" className="@container">
      <CardHeader>
        <CardTitle id="mcp-http-title">MCP over HTTP</CardTitle>
        <p className={META}>Clients share this running server and need a token. The endpoint is off until you turn it on.</p>
      </CardHeader>
      {state === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className={META}>
            Loading.
          </p>
        )
      ) : (
        <div data-slot="mcp-columns" className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 @3xl:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-3">
            <DenseSettingRows>
              <div className="flex min-w-0 flex-col">
                <SettingBox>
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <p className={META}>Endpoint</p>
                      <p className={META}>{sourceText(state.source)}</p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      role="switch"
                      aria-checked={state.enabled}
                      aria-label="MCP over HTTP"
                      disabled={change.isPending || isEnvironmentSource(state.source)}
                      onClick={() => change.mutate(!state.enabled)}
                    >
                      {change.isPending ? "Saving" : state.enabled ? "On" : "Off"}
                    </Button>
                  </div>
                  {change.isError ? <SaveErrorNotice error={change.error} onRetry={() => change.reset()} /> : null}
                </SettingBox>
                <SettingBox>
                  <p className={META}>URL</p>
                  <code dir="ltr" className={CODE}>
                    {state.url}
                  </code>
                </SettingBox>
              </div>
              <McpTokenPanel />
              <WebPortPanel />
            </DenseSettingRows>
          </div>
          <ClientConfiguration text={httpConfiguration(state.url)} what="HTTP configuration" />
        </div>
      )}
    </Card>
  );
}
