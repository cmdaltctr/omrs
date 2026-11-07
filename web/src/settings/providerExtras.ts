import type { ComponentType } from "react";
import { LlamacppRouterPanel } from "./LlamacppRouterPanel";

/** A panel a provider card shows below its fields, at full width. */
export interface ProviderExtra {
  Component: ComponentType;
  /** Field ids and read-only labels that the panel shows itself, so the card leaves them out. */
  replaces: readonly string[];
}

/**
 * Extra panels of a provider card, by provider id. The llama.cpp card shows one
 * Router panel: who runs llama.cpp, its address, its limits and its model list.
 * A card with no entry shows nothing extra.
 */
export const PROVIDER_EXTRAS: Record<string, readonly ProviderExtra[] | undefined> = {
  llamacpp: [{ Component: LlamacppRouterPanel, replaces: ["router_url", "Router mode"] }],
};
