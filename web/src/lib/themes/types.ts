/** The colours of one theme, by the OMRS token they set. */
export interface ThemeColours {
  canvas: string;
  elevated: string;
  muted: string;
  text: string;
  textSecondary: string;
  border: string;
  borderHover: string;
  accent: string;
  accentHover: string;
  accentActive: string;
  selection: string;
  hover: string;
  active: string;
  focus: string;
  error: string;
  warning: string;
  success: string;
  info: string;
}

export interface ThemeDefinition {
  id: string;
  /** The palette name, shared by the light and dark member of a pair. */
  name: string;
  variant: "light" | "dark";
  author?: string;
  colours: ThemeColours;
}
