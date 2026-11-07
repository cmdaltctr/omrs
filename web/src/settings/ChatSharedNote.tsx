import type { ChatSettings } from "../api/settings";
import { useLlamacppRouter } from "../api/llamacppRouterHooks";
import { formatRoute } from "../lib/routes";
import { SHARED_NOTE } from "./llamacppRouterWords";
import { ServerCallout } from "./ServerCallout";

const PROVIDERS = formatRoute({ area: "settings", section: "providers" });
const LINK = "text-primary-label underline underline-offset-4";

/** True when Chat runs on llama.cpp with the classification model: both names are the same. */
export function sharesClassification(settings: ChatSettings, classification: string | undefined): boolean {
  return settings.provider === "llamacpp" && (settings.model ?? "") !== "" && settings.model === classification;
}

/**
 * The note in Settings > Chat while Chat uses the classification model, with
 * three ways out. It does not block Save. "Choose another local model" opens
 * the Chat form; the other two lead to the Providers page.
 */
export function ChatSharedNote({ settings, onChooseAnother }: { settings: ChatSettings; onChooseAnother: () => void }) {
  const router = useLlamacppRouter().data;
  const classification = router?.models.find((entry) => entry.roles.includes("classification"))?.model;
  if (!sharesClassification(settings, classification)) return null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ServerCallout tone="warning" text={SHARED_NOTE} />
      <ul aria-label="Ways to keep them apart" className="list-disc ps-5 text-ui">
        <li>
          <button type="button" className={LINK} onClick={onChooseAnother}>
            Choose another local model on the router
          </button>
          .
        </li>
        <li>
          {"Use your own llama.cpp server for Chat through the "}
          <a href={PROVIDERS} className={LINK}>
            OpenAI-compatible provider
          </a>
          . OMRS does not run it.
        </li>
        <li>
          {"Use a "}
          <a href={PROVIDERS} className={LINK}>
            hosted provider
          </a>
          {" such as OpenRouter."}
        </li>
      </ul>
    </div>
  );
}
