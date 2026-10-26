import { Plug } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { PluginState } from "../api/plugins";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Check, TextField } from "./fields";
import { pluginStatusLabel } from "./labels";
import { useRecheckPlugin, useRegisterPlugin } from "./mutations";

function describe(state: PluginState): string {
  return `Registered ${state.name}: ${pluginStatusLabel(state.status)}. ${state.message}`;
}

interface PluginRegisterFormProps {
  /** The manifest that the installed application ships, or null. */
  shippedManifest?: string | null;
  /** The marimo executable that the server found in its uv tool environment, or null. */
  detectedExecutable?: string | null;
}

/**
 * Registers an approved manifest and executable. Registration itself runs no
 * process and installs nothing. Until the user types, the manifest path holds
 * the manifest that the installed application ships and the executable path
 * holds the marimo the server found, when the server names them. After a
 * registration the form runs one compatibility check, so the plugin leaves
 * the unchecked state without another click.
 */
export function PluginRegisterForm({ shippedManifest = null, detectedExecutable = null }: PluginRegisterFormProps) {
  const register = useRegisterPlugin();
  const recheck = useRecheckPlugin();
  const [typedManifest, setManifestPath] = useState<string | null>(null);
  const manifestPath = typedManifest ?? shippedManifest ?? "";
  const [typedExecutable, setExecutablePath] = useState<string | null>(null);
  const executablePath = typedExecutable ?? detectedExecutable ?? "";
  const [approved, setApproved] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const ready = approved && manifestPath.trim() !== "" && executablePath.trim() !== "" && !register.isPending && !recheck.isPending;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setDone(null);
    try {
      const registered = await register.mutateAsync({ manifestPath: manifestPath.trim(), executablePath: executablePath.trim(), approved });
      setApproved(false);
      setDone(describe(registered));
      setDone(describe(await recheck.mutateAsync(registered.name)));
    } catch {
      // The mutation holds the error, which renders below.
    }
  }

  return (
    <form aria-label="Register a plugin" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3 border-t border-border pt-3">
      <h4 className="text-subsection-title font-semibold">Register a plugin</h4>
      <p className="text-meta text-muted-foreground">
        Use the shipped manifest or one below the workspace plugins folder. The executable must be on the server&apos;s PATH, below that folder, or the
        marimo that the marimo card found.
      </p>
      <div className="flex flex-wrap gap-3">
        <TextField label="Manifest path" dir="ltr" value={manifestPath} onChange={setManifestPath} />
        <TextField label="Executable path" dir="ltr" value={executablePath} onChange={setExecutablePath} />
      </div>
      <Check checked={approved} onChange={setApproved}>
        I approve this manifest and executable. Notebooks they open run Python with my permissions.
      </Check>
      <div>
        <Button type="submit" disabled={!ready}>
          <Plug aria-hidden="true" />
          Register plugin
        </Button>
      </div>
      {register.isError ? <ErrorNotice error={register.error} /> : null}
      {recheck.isError ? <ErrorNotice error={recheck.error} /> : null}
      {done !== null ? (
        <p role="status" className="text-meta [overflow-wrap:anywhere]">
          {done}
        </p>
      ) : null}
    </form>
  );
}
