import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { useLlamacppServer } from "../api/llamacppServerHooks";
import { chatSettingsQuery, connectionsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { SettingBox } from "./SettingBox";
import { ChatModelRow, ChatSettingsLink } from "./ChatModelRow";
import { ChatServerChoice } from "./ChatServerChoice";
import { chatUsesLine } from "./chatServerWords";
import { LlamacppServerPanel } from "./LlamacppServerPanel";

/**
 * The Chat model in force, read-only. With Chat on llama.cpp it is the row
 * "Chat model"; with another provider one line names that provider and model.
 * Both link to Settings > Chat.
 */
function ChatModelLine() {
  const api = useApi();
  const chat = useQuery(chatSettingsQuery(api));
  const providers = useQuery(connectionsQuery(api));
  const settings = chat.data;
  if (settings === undefined) return chat.isError ? <ErrorNotice error={chat.error} onRetry={() => void chat.refetch()} /> : null;
  if (settings.provider === "llamacpp") return <ChatModelRow model={settings.model ?? ""} />;
  const name = providers.data?.connections.find((connection) => connection.provider === settings.provider)?.display_name ?? settings.provider ?? "Not chosen";
  return (
    <SettingBox>
      <p className="text-ui">{chatUsesLine(name, settings.model ?? "")}</p>
      <div>
        <ChatSettingsLink />
      </div>
    </SettingBox>
  );
}

/** Who runs the Chat server and, when OMRS runs it, the Local server panel. The saved choice decides, not the server state. */
function ChatServer() {
  const query = useLlamacppServer();
  const status = query.data;
  if (status === undefined) return query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null;
  return (
    <>
      <ChatServerChoice status={status} />
      {status.saved.chat_server.value === "managed" ? <LlamacppServerPanel status={status} /> : null}
    </>
  );
}

/** The Chat block of the llama.cpp card, after the Chat address: the Chat model, who runs the Chat server, and OMRS's own server. */
export function LlamacppChatBlock() {
  return (
    <>
      <ChatModelLine />
      <ChatServer />
    </>
  );
}
