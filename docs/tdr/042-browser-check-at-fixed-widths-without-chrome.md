# TDR-042: Browser check at fixed widths without Chrome

- **Date:** 2026-10-29
- **Status:** Accepted (2026-10-30)
- **Deciders:** Maintainer
- **Tags:** web | browser-check | testing | macOS

## Context

Every web change needs screenshots of the page at 1280 px and 390 px. During the
`separate-local-chat-and-classification` build, three usual routes failed:

1. **Chrome DevTools MCP.** It looks for `/Applications/Google Chrome.app` and stops
   with "Could not find Google Chrome executable". This Mac has no Chrome.
2. **Orca browser tab.** The tab has the width of the Orca pane (756 px on this run).
   The `orca` CLI has no option to set the width.
3. **Frames in one tab.** A same-origin page with a 1280 px frame and a 390 px frame
   does not work. `contentDocument` is `null`, because `omrs web` refuses to be
   framed.

### Root cause

The check needs a browser whose viewport width can be set exactly. Only a DevTools
protocol (CDP) client can set it (`Emulation.setDeviceMetricsOverride`). The only
browser on this Mac that speaks CDP is Microsoft Edge.

## Decision

Run Microsoft Edge headless with its own scratch profile. Drive it with a short
Node script over CDP. Node 22 and later has a built-in `WebSocket`, so nothing is
installed.

1. Start Edge with a scratch profile:

   ```bash
   "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" --headless=new \
     --remote-debugging-port=9333 --user-data-dir=<scratch>/edge-profile \
     --no-first-run --disable-gpu about:blank &
   ```

2. Start a scratch `omrs web` and read the one-time `#bootstrap=` token from its log.
3. In the script: `PUT /json/new` gives a page. Open `http://127.0.0.1:<port>/#bootstrap=<token>`.
   Then, for each width, call `Emulation.setDeviceMetricsOverride` and open the page
   route. Call `Page.captureScreenshot`.
4. In the same script, read `document.documentElement.scrollWidth`. It must equal the
   width, so nothing scrolls sideways.
5. Stop only the scratch processes: `pkill -f "user-data-dir=<scratch>/edge-profile"`
   and `pkill -f "omrs web --workspace <scratch>"`.

A sign-in token works once. Restart the scratch server to get a new token for a
second browser.

## Consequences

- **Positive:** exact widths, full control of the page state, and facts read from
  the DOM (block titles, callout text) next to each screenshot.
- **Positive:** the user's Edge profile and the live app are not touched.
- **Negative:** the script is not in the repository. Each run writes it again.
- **Neutral:** Orca stays the tool for a page the user looks at.

## Alternatives Considered

| Option | Why not |
| --- | --- |
| Install Chrome | Asks for a new install on the user's machine. |
| Install Playwright | Adds a large dependency for one check. |
| Orca tab at pane width | Neither 1280 px nor 390 px. |
| Frames in one tab | `omrs web` refuses to be framed. |

## How to Recognise / Handle This Again

- Chrome DevTools MCP reports "Could not find Google Chrome executable": use Edge as above.
- `orca eval ... window.innerWidth` is not the width you need: use Edge as above.
- `ls /Applications | grep -i edge` shows whether Edge is there.

## Revisit Triggers

- Chrome or Playwright is installed on this Mac.
- The Orca CLI gets an option to set the viewport width.
- The repository gets a browser test runner.

## References

- `openspec/changes/separate-local-chat-and-classification/live-checks.md`, section 3
- `openspec/changes/separate-local-chat-and-classification/screenshots/`
- [ADR-108](../adr/108-local-chat-and-classification-stay-apart.md)
