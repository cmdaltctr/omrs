import { useQuery } from "@tanstack/react-query";
import { SquareArrowOutUpRight } from "lucide-react";
import { useState } from "react";
import { useApi } from "../../api/ApiProvider";
import { ClientRefusal } from "../../api/client";
import type { NotebookState } from "../../api/experimentEditor";
import { useOpenExperimentEditor } from "../../api/experimentLibraryMutations";
import { editorTabUrl, editorToken, type EditorInfo } from "../../api/plugins";
import { pluginsQuery } from "../../api/queries";
import { AlertNotice } from "../../components/AlertNotice";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { formatRoute } from "../../lib/routes";
import { useReturnFocus } from "../../studio/useReturnFocus";
import { ConfirmAction } from "../ConfirmAction";
import { STOP_WARNING } from "../EditorList";
import { Check } from "../fields";
import { useStopEditor } from "../mutations";
import { OneTimeSecret } from "../OneTimeSecret";
import { editorRefusalLine } from "./refusal";

const CODE_EDITOR = formatRoute({ area: "experiments", section: "code-editor" });

const STATE_LINES: Record<NotebookState, string> = {
  converted: "Converted from analysis.py.",
  created: "Created an empty notebook.",
  existing: "Opened the existing notebook.",
};

/** What one open returned. The token lives in component state only, until the user hides it. */
interface Opened {
  launchId: string;
  url: string;
  token: string | null;
  notebookState: NotebookState;
  sourceNewer: boolean;
  shadowed: string[];
}

/**
 * State for "Open in marimo" on one experiment page: whether marimo can
 * launch, the editor this experiment already runs (found in the plugin list
 * by project and folder), the consent dialog and the last open.
 */
export function useMarimoLauncher(projectId: string, folder: string) {
  const plugins = useQuery(pluginsQuery(useApi()));
  const open = useOpenExperimentEditor();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [consent, setConsent] = useState(false);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const marimo = plugins.data?.plugins.find((plugin) => plugin.name === "marimo");
  const launchable = marimo !== undefined && marimo.launchable && marimo.status === "compatible";
  const running = plugins.data?.editors.find((editor) => editor.project_id === projectId && editor.folder === folder) ?? null;

  function showDialog() {
    // Consent is never remembered: every open asks again.
    setConsent(false);
    setDialogOpen(true);
  }

  async function confirm() {
    if (!consent || open.isPending) return;
    setRefusal(null);
    try {
      const response = await open.mutateAsync({ projectId, folder });
      const token = editorToken(response);
      const url = editorTabUrl(response);
      window.open(url, "_blank", "noopener,noreferrer");
      const { notebook_state: notebookState, source_newer: sourceNewer, environment } = response;
      setOpened({ launchId: response.launch_id, url, token, notebookState, sourceNewer, shadowed: environment.shadowed });
    } catch (failure) {
      setRefusal(failure instanceof ClientRefusal ? failure.message : editorRefusalLine(failure));
    } finally {
      setConsent(false);
      setDialogOpen(false);
    }
  }

  return {
    launchable,
    checked: !plugins.isPending,
    running,
    opened,
    refusal,
    dialogOpen,
    consent,
    busy: open.isPending,
    setConsent,
    showDialog,
    closeDialog: () => {
      // The dialog stays open while the server opens marimo.
      if (!open.isPending) setDialogOpen(false);
    },
    confirm: () => void confirm(),
    hideToken: () => setOpened((current) => (current === null ? null : { ...current, token: null })),
    clearOpened: () => setOpened(null),
  };
}

export type MarimoLauncher = ReturnType<typeof useMarimoLauncher>;

/** The header button and its consent dialog. */
export function OpenInMarimoButton({ launcher }: { launcher: MarimoLauncher }) {
  const returnFocus = useReturnFocus();
  return (
    <>
      <Button className="w-full sm:w-auto" disabled={!launcher.launchable} onClick={launcher.showDialog}>
        <SquareArrowOutUpRight aria-hidden="true" />
        Open in marimo
      </Button>
      <Dialog open={launcher.dialogOpen} onOpenChange={(next) => (next ? undefined : launcher.closeDialog())}>
        <DialogContent {...returnFocus}>
          <DialogHeader>
            <DialogTitle>Open in marimo</DialogTitle>
            <DialogDescription>
              {"This opens "}
              <code className="text-code">analysis.marimo.py</code>
              {" in marimo in a new tab. The notebook runs in this project's Python environment with your full file and network access, like any program you start. OMRS does not sandbox it. Cells do not run until you run them. OMRS adds "}
              <code className="text-code">analysis.marimo.py</code>
              {" and marimo adds "}
              <code className="text-code">__marimo__/</code>
              {" in the experiment folder. Add both to your "}
              <code className="text-code">.gitignore</code>
              {"."}
            </DialogDescription>
          </DialogHeader>
          <Check checked={launcher.consent} onChange={launcher.setConsent}>
            I understand this notebook runs with my full access
          </Check>
          <p role="status" className="sr-only">
            {launcher.busy ? "Opening marimo" : ""}
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={launcher.busy} onClick={launcher.closeDialog}>
              Cancel
            </Button>
            <Button type="button" disabled={!launcher.consent || launcher.busy} aria-busy={launcher.busy} onClick={launcher.confirm}>
              <SquareArrowOutUpRight aria-hidden="true" />
              {launcher.busy ? "Opening marimo" : "Open in marimo"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function EditorAddress({ url }: { url: string }) {
  return (
    <p className="text-meta">
      {"Editor address: "}
      <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
        {url}
      </code>
    </p>
  );
}

function TabLink({ url, children }: { url: string; children: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="w-fit text-ui text-primary-label underline underline-offset-4">
      {children}
    </a>
  );
}

function StopEditor({ launchId, onStopped }: { launchId: string; onStopped?: () => void }) {
  const stop = useStopEditor();
  return (
    <div>
      <ConfirmAction
        label={`Stop editor ${launchId}`}
        text="Stop"
        warning={STOP_WARNING}
        confirmLabel="Confirm stop"
        cancelLabel="Keep running"
        onConfirm={async () => {
          await stop.mutateAsync(launchId);
          onStopped?.();
        }}
      />
    </div>
  );
}

function OpenedCard({ opened, onHide, onStopped }: { opened: Opened; onHide: () => void; onStopped: () => void }) {
  return (
    <>
      <h3 className="text-subsection-title font-semibold">marimo is open in a new tab</h3>
      <EditorAddress url={opened.url} />
      {opened.token !== null ? (
        <OneTimeSecret title="Editor access token" secret={opened.token} onHide={onHide}>
          <p className="text-meta">Paste it into the marimo sign-in page.</p>
        </OneTimeSecret>
      ) : null}
      <TabLink url={opened.url}>Open the editor tab again</TabLink>
      <p className="text-ui">{STATE_LINES[opened.notebookState]}</p>
      {opened.sourceNewer ? (
        <p className="text-ui text-status-warning-label">analysis.py changed after this notebook was made. Delete analysis.marimo.py to make a new copy.</p>
      ) : null}
      {opened.shadowed.length > 0 ? (
        <p className="text-ui text-status-warning-label [overflow-wrap:anywhere]">
          {`marimo loads its own copy of these packages first, so their versions can differ from the project's: ${opened.shadowed.join(", ")}.`}
        </p>
      ) : null}
      <StopEditor launchId={opened.launchId} onStopped={onStopped} />
    </>
  );
}

function RunningCard({ editor }: { editor: EditorInfo }) {
  let url: string | null = null;
  try {
    url = editorTabUrl(editor);
  } catch {
    // An address the page refuses to open gets no link.
  }
  return (
    <>
      <h3 className="text-subsection-title font-semibold">marimo is running for this experiment</h3>
      <EditorAddress url={editor.url_without_token} />
      {url !== null ? <TabLink url={url}>Open the editor tab</TabLink> : null}
      <p className="text-meta text-muted-foreground">The token was shown once when the editor opened. Stop the editor and open it again to get a new token.</p>
      <StopEditor launchId={editor.launch_id} />
    </>
  );
}

/** Below the record card: the hint, a refused open, and the opened or running editor with Stop. */
export function MarimoEditorStatus({ launcher }: { launcher: MarimoLauncher }) {
  const { opened, running } = launcher;
  return (
    <>
      {launcher.checked && !launcher.launchable ? (
        <p className="text-meta text-muted-foreground">
          {"Register marimo in Experiments, "}
          <a href={CODE_EDITOR} className="text-primary-label underline underline-offset-4">
            Code editor
          </a>
          {", to open notebooks."}
        </p>
      ) : null}
      {launcher.refusal !== null ? (
        <AlertNotice message={launcher.refusal}>
          <Button variant="outline" disabled={!launcher.launchable} onClick={launcher.showDialog}>
            Try again
          </Button>
        </AlertNotice>
      ) : null}
      {opened !== null || running !== null ? (
        <section aria-label="marimo editor">
          <Card>
            {opened !== null ? (
              <OpenedCard opened={opened} onHide={launcher.hideToken} onStopped={launcher.clearOpened} />
            ) : running !== null ? (
              <RunningCard editor={running} />
            ) : null}
          </Card>
        </section>
      ) : null}
    </>
  );
}
