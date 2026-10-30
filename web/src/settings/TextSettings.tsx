import { Minus, Plus } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { CODE_FONTS, TEXT_SIZE, UI_FONTS, type FontOption } from "../lib/fonts";
import { usePreferences } from "../lib/PreferencesProvider";
import { DenseSettingRows, SettingBox } from "./SettingBox";

const META = "text-meta text-muted-foreground";

/** One setting with its label and hint left and its control right. */
function ControlRow({ label, hint, labelId, children }: { label: string; hint: string; labelId: string; children: ReactNode }) {
  return (
    <SettingBox>
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p id={labelId} className="text-ui">
            {label}
          </p>
          <p className={META}>{hint}</p>
        </div>
        {children}
      </div>
    </SettingBox>
  );
}

function FontSelect({ labelId, options, value, onChange }: { labelId: string; options: readonly FontOption[]; value: string; onChange: (id: string) => void }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-labelledby={labelId} className="w-52">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.id} value={option.id}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** The interface font, the code font and the text size. Each change applies at once and stays in this browser. */
export function TextSettings() {
  const { preferences, setAppearance } = usePreferences();
  const id = useId();
  const size = preferences.textSize;
  const resize = (next: number) => setAppearance({ textSize: Math.min(TEXT_SIZE.max, Math.max(TEXT_SIZE.min, next)) });

  return (
    <Card aria-labelledby={`${id}-title`}>
      <CardHeader>
        <CardTitle id={`${id}-title`}>Text</CardTitle>
        <p className={META}>Bundled fonts load from this server only when you choose them.</p>
      </CardHeader>
      <DenseSettingRows>
        <div className="flex min-w-0 flex-col">
          <ControlRow label="Interface font" hint="Menus, labels and answers." labelId={`${id}-ui`}>
            <FontSelect labelId={`${id}-ui`} options={UI_FONTS} value={preferences.uiFont} onChange={(uiFont) => setAppearance({ uiFont })} />
          </ControlRow>
          <ControlRow label="Code font" hint="Paths, values and code." labelId={`${id}-code`}>
            <FontSelect labelId={`${id}-code`} options={CODE_FONTS} value={preferences.codeFont} onChange={(codeFont) => setAppearance({ codeFont })} />
          </ControlRow>
          <ControlRow label="Text size" hint={`Scales the whole interface. ${TEXT_SIZE.min} % to ${TEXT_SIZE.max} %.`} labelId={`${id}-size`}>
            <div role="group" aria-labelledby={`${id}-size`} className="flex items-center gap-1">
              <Button variant="outline" size="icon" aria-label="Smaller text" disabled={size <= TEXT_SIZE.min} onClick={() => resize(size - TEXT_SIZE.step)}>
                <Minus aria-hidden="true" />
              </Button>
              <output aria-live="polite" className="w-14 text-center font-mono text-code tabular-nums">{`${size} %`}</output>
              <Button variant="outline" size="icon" aria-label="Larger text" disabled={size >= TEXT_SIZE.max} onClick={() => resize(size + TEXT_SIZE.step)}>
                <Plus aria-hidden="true" />
              </Button>
              <Button variant="ghost" size="sm" disabled={size === TEXT_SIZE.default} onClick={() => resize(TEXT_SIZE.default)}>
                Reset
              </Button>
            </div>
          </ControlRow>
        </div>
      </DenseSettingRows>
    </Card>
  );
}
