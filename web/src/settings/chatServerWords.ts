/**
 * Words of the Chat block on the llama.cpp card (design D8 and D9). They live
 * in one file so tests pin them.
 */
import type { ChatServerChoice } from "../api/llamacppServer";

/** The link from the card to Settings > Chat, the only place that sets the Chat model. */
export const CHAT_LINK_TEXT = "Change in Settings > Chat";

/** The Chat model line when Chat uses a provider other than llama.cpp, such as "Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)". */
export function chatUsesLine(provider: string, model: string): string {
  return model === "" ? `Chat uses ${provider}` : `Chat uses ${provider} (${model})`;
}

/** The label of the Chat server choice. */
export const CHAT_SERVER_LABEL = "Who runs the Chat server";

/** The two options of the Chat server choice. */
export const CHOICE_NAMES: Record<ChatServerChoice, string> = {
  external: "The Llama app or another server you run",
  managed: "OMRS's own llama-server",
};

/** The callout of each choice (design D9). The `managed` one also shows above the program path row while that path is not usable. */
export const CALLOUTS: Record<ChatServerChoice, string> = {
  external:
    "Context size: set ctx-size for this model in the Llama app's models.user.ini, then relaunch the Llama app. The relaunch pauses embeddings and anything else on that port. OMRS does not edit this file or restart the app.",
  managed:
    "OMRS's own server needs a program named exactly llama-server. The Llama app's own llama program does not qualify. Install one with Homebrew: brew install llama.cpp. Then set the program path, for example /opt/homebrew/bin/llama-server.",
};
