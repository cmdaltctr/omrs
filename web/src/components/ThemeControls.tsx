import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { usePreferences } from "../lib/PreferencesProvider";
import { THEMES, type ThemePreference } from "../lib/preferences";
import { NavTooltip } from "./NavTooltip";
import { Button } from "./ui/button";

const LABELS: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };
const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** The theme in effect: the preference, or the operating system's choice for System. */
export function useEffectiveTheme(): "light" | "dark" {
  const { preferences } = usePreferences();
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DARK_QUERY);
    const update = () => setSystemDark(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  if (preferences.theme === "system") return systemDark ? "dark" : "light";
  return preferences.theme;
}

/** System, Light and Dark as three chips. Settings > Appearance shows it. */
export function ThemeModeChips() {
  const { preferences, setTheme } = usePreferences();
  return (
    <div role="group" aria-label="Theme mode" className="flex flex-wrap gap-2">
      {THEMES.map((theme) => (
        <Button key={theme} variant="chip" size="sm" aria-pressed={preferences.theme === theme} onClick={() => setTheme(theme)}>
          {LABELS[theme]}
        </Button>
      ))}
    </div>
  );
}

/** One click between Light and Dark. It shows the theme in effect and names the one it switches to. */
export function ThemeToggle({ withTooltip = false }: { withTooltip?: boolean }) {
  const { setTheme } = usePreferences();
  const effective = useEffectiveTheme();
  const target = effective === "dark" ? "light" : "dark";
  const Icon = effective === "dark" ? Moon : Sun;
  const label = `Switch to ${target} theme`;
  const button = (
    <Button variant="ghost" size="icon" aria-label={label} onClick={() => setTheme(target)}>
      <Icon aria-hidden="true" />
    </Button>
  );
  return withTooltip ? <NavTooltip label={label}>{button}</NavTooltip> : button;
}
