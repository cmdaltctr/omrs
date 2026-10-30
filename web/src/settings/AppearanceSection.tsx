import { useState } from "react";
import { ThemeModeChips, useEffectiveTheme } from "../components/ThemeControls";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { usePreferences } from "../lib/PreferencesProvider";
import { TextSettings } from "./TextSettings";
import { ThemeList } from "./ThemeList";

/**
 * Settings > Appearance: the theme mode, a light and a dark theme, fonts and
 * text size. Every choice stays in this browser. The top bar's theme switch
 * reads and writes the same mode. Themes come from OpenChamber (MIT).
 */
export function AppearanceSection() {
  const { preferences, setAppearance } = usePreferences();
  const effective = useEffectiveTheme();
  const [filter, setFilter] = useState("");
  const needle = filter.trim().toLowerCase();

  return (
    <section aria-labelledby="settings-appearance" className="flex flex-col gap-3">
      <h2 id="settings-appearance" className="text-section-title font-semibold">
        Appearance
      </h2>
      <Card aria-labelledby="settings-theme" className="@container">
        <CardHeader>
          <CardTitle id="settings-theme">Theme</CardTitle>
          <p className="text-meta text-muted-foreground">System follows your operating system and switches between the light and the dark theme. The choice stays in this browser.</p>
        </CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ThemeModeChips />
          <Input type="search" aria-label="Filter themes" placeholder="Filter themes" value={filter} onChange={(event) => setFilter(event.target.value)} className="w-full @xl:w-60" />
        </div>
        <div data-slot="theme-columns" className="grid min-w-0 grid-cols-1 gap-x-6 gap-y-4 @xl:grid-cols-2">
          <ThemeList variant="light" selected={preferences.lightTheme} filter={needle} inUse={effective === "light"} onSelect={(lightTheme) => setAppearance({ lightTheme })} />
          <ThemeList variant="dark" selected={preferences.darkTheme} filter={needle} inUse={effective === "dark"} onSelect={(darkTheme) => setAppearance({ darkTheme })} />
        </div>
      </Card>
      <TextSettings />
    </section>
  );
}
