import { SettingBox } from "./SettingBox";
import { formatRoute } from "../lib/routes";
import { CHAT_LINK_TEXT } from "./chatServerWords";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

/** A link to Settings > Chat, where the Chat model is set. */
export function ChatSettingsLink() {
  return (
    <a href={formatRoute({ area: "settings", section: "chat" })} className="text-primary-label underline underline-offset-4">
      {CHAT_LINK_TEXT}
    </a>
  );
}

/** The Chat model as a read-only row. Settings > Chat sets it, so the row links there and offers no Edit. */
export function ChatModelRow({ model }: { model: string }) {
  return (
    <SettingBox>
      <p className="text-meta text-muted-foreground">
        Chat model <span>(Read-only)</span>
      </p>
      {model === "" ? (
        <p className="text-ui">Not set</p>
      ) : (
        <code dir="ltr" className={CODE}>
          {model}
        </code>
      )}
      <div>
        <ChatSettingsLink />
      </div>
    </SettingBox>
  );
}
