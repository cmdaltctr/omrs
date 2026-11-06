import { useState } from "react";
import { useInstallLlamacppBuild, useLlamacppBuild } from "../api/llamacppInstallHooks";
import type { InstallJobReason, LlamacppBuild as Build, LlamacppFlavour } from "../api/llamacppInstall";
import { useLlamacppRouter } from "../api/llamacppRouterHooks";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { CONFLICT_SENTENCES, conflictReason } from "../settings/llamacppRouterWords";
import { useScopes } from "../settings/useScopes";

const META = "text-meta text-muted-foreground";

/** The plain line of each fixed reason, said when the server sends no line of its own. */
export const INSTALL_SENTENCES: Record<InstallJobReason, string> = {
  "not-supported": "OMRS has no pinned build for this system. Install llama.cpp yourself and set the program path.",
  "download-failed": "The archive could not be downloaded. Check the connection, then try again.",
  "file-changed": "The downloaded archive does not match its recorded SHA-256, so it was not used.",
  "binary-check-failed": "The build did not run on this system.",
  "cuda-device-missing": "No NVIDIA device was found, so the CUDA build cannot run here. Choose CPU, or install the driver.",
  failed: "The install failed. Try again.",
};

const FLAVOUR_NAMES: Record<LlamacppFlavour, string> = { cpu: "CPU", cuda: "CUDA 12.8" };

/** The radio labels, with "(detected)" on the flavour that fits this host. */
function flavourLabel(flavour: LlamacppFlavour, detected: Build["detected"]): string {
  return flavour === detected ? `${FLAVOUR_NAMES[flavour]} (detected)` : FLAVOUR_NAMES[flavour];
}

function FlavourChoice({ build, value, onChange }: { build: Build; value: LlamacppFlavour | null; onChange: (flavour: LlamacppFlavour) => void }) {
  return (
    <div role="radiogroup" aria-label="Build to install" className="flex flex-wrap gap-x-4 gap-y-1">
      {build.choices.map((flavour) => (
        <label key={flavour} className="flex items-center gap-2 text-ui">
          <input type="radio" name="llamacpp-flavour" className="size-4 accent-primary" checked={value === flavour} onChange={() => onChange(flavour)} />
          {flavourLabel(flavour, build.detected)}
        </label>
      ))}
    </div>
  );
}

/**
 * The pinned llama.cpp build on the llama.cpp card: the pinned tag, whether a
 * program is placed, the flavour choice (Linux x86-64 only) and Get llama.cpp.
 * The button needs `manage`. A failed job shows one reason line and leaves the
 * program unplaced. A program path the user set is the program in force, so the
 * card says that and offers no build.
 */
export function LlamacppBuild() {
  const query = useLlamacppBuild();
  const install = useInstallLlamacppBuild();
  const scopes = useScopes();
  const router = useLlamacppRouter();
  const [picked, setPicked] = useState<LlamacppFlavour | null>(null);
  const build = query.data;
  if (router.data?.program.source === "user")
    return (
      <p className={META}>
        {"Uses your own program: "}
        <code dir="ltr" className="text-code [overflow-wrap:anywhere]">
          {router.data.program.path}
        </code>
      </p>
    );
  if (build === undefined) return query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null;

  const detected = build.detected === "cpu" || build.detected === "cuda" ? build.detected : null;
  const flavour = picked ?? detected;
  const running = build.job.state === "running" || install.isPending;
  const failed = build.job.state === "failed" && build.job.reason !== null;
  const conflict = install.isError ? conflictReason(install.error) : null;

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <p className={META}>
        {`llama.cpp build ${build.build}. `}
        {build.installed_path === null ? (
          "Not installed"
        ) : (
          <>
            {"Installed at "}
            <code dir="ltr" className="text-code [overflow-wrap:anywhere]">
              {build.installed_path}
            </code>
          </>
        )}
      </p>
      {build.installed_path === null && build.choices.length > 0 ? <FlavourChoice build={build} value={flavour} onChange={setPicked} /> : null}
      {build.job.state === "running" && build.job.line !== null ? <p className={META}>{build.job.line}</p> : null}
      {failed ? <p className="text-ui [overflow-wrap:anywhere]">{`Failed: ${build.job.message ?? INSTALL_SENTENCES[build.job.reason!]}`}</p> : null}
      {build.installed_path === null && scopes.has("manage") ? (
        <div>
          <Button type="button" size="sm" variant="outline" disabled={running} onClick={() => install.mutate(flavour)}>
            Get llama.cpp
          </Button>
        </div>
      ) : null}
      {conflict !== null ? (
        <p role="alert" className="text-ui text-status-error-label">
          {CONFLICT_SENTENCES[conflict]}
        </p>
      ) : null}
      {install.isError && conflict === null ? <ErrorNotice error={install.error} onRetry={() => install.reset()} /> : null}
    </div>
  );
}
