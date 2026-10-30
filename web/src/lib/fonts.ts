/**
 * The font choices of Settings > Appearance. Each bundled font is an OFL
 * Fontsource package served by this server; its stylesheet loads only when
 * the font is chosen, so the default System fonts download nothing.
 */
export interface FontOption {
  id: string;
  label: string;
  /** The CSS font-family stack, ending in the system fallback. */
  stack: string;
  load?: () => Promise<unknown>;
}

const SANS_FALLBACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
const MONO_FALLBACK = 'ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace';

export const UI_FONTS: readonly FontOption[] = [
  { id: "system", label: "System", stack: SANS_FALLBACK },
  { id: "inter", label: "Inter", stack: `"Inter Variable", ${SANS_FALLBACK}`, load: () => import("@fontsource-variable/inter/index.css") },
  { id: "geist", label: "Geist", stack: `"Geist Variable", ${SANS_FALLBACK}`, load: () => import("@fontsource-variable/geist/index.css") },
  {
    id: "atkinson-hyperlegible",
    label: "Atkinson Hyperlegible",
    stack: `"Atkinson Hyperlegible", ${SANS_FALLBACK}`,
    load: () => Promise.all([import("@fontsource/atkinson-hyperlegible/400.css"), import("@fontsource/atkinson-hyperlegible/700.css")]),
  },
  { id: "source-sans-3", label: "Source Sans 3", stack: `"Source Sans 3 Variable", ${SANS_FALLBACK}`, load: () => import("@fontsource-variable/source-sans-3/index.css") },
];

export const CODE_FONTS: readonly FontOption[] = [
  { id: "system", label: "System mono", stack: MONO_FALLBACK },
  { id: "jetbrains-mono", label: "JetBrains Mono", stack: `"JetBrains Mono Variable", ${MONO_FALLBACK}`, load: () => import("@fontsource-variable/jetbrains-mono/index.css") },
  { id: "fira-code", label: "Fira Code", stack: `"Fira Code Variable", ${MONO_FALLBACK}`, load: () => import("@fontsource-variable/fira-code/index.css") },
  { id: "geist-mono", label: "Geist Mono", stack: `"Geist Mono Variable", ${MONO_FALLBACK}`, load: () => import("@fontsource-variable/geist-mono/index.css") },
];

/** The option with this id, or System. */
export function findFont(options: readonly FontOption[], id: string): FontOption {
  return options.find((option) => option.id === id) ?? options[0]!;
}

/** Text size as a percentage of the browser's root size. Every size in tokens.css is in rem, so the whole interface scales. */
export const TEXT_SIZE = { min: 80, max: 150, step: 5, default: 100 } as const;
