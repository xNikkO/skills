# Testing the running app and capturing evidence

Passing unit tests do not show that a feature works. The implementer must use the change the way a user would, and say exactly what it did. This applies to the first implementation and to every repair.

## What to exercise

| Change | How to verify it |
| --- | --- |
| Web UI | Start the app and open it with the T3 preview tools. Walk through each acceptance criterion: click, type, submit, navigate. Check the browser console and failed network requests. |
| HTTP API or backend | Start the server and send real requests for the success case and for each failure the change handles. Check status, body and the stored result. |
| CLI or script | Run it with real arguments, including a bad input. |
| Mobile | Use the T3 device tools on an open device or simulator. |
| Library code with no entry point | Run a short script that calls the changed code, in addition to the tests. |

Also run the repository's own checks: tests, linter, type check, build, and coverage when the task sets a threshold. Report the measured coverage figure, not "passes".

If the app cannot be started, say why and what was tried. The affected criteria are then `unverified`, which blocks the gate until the user waives them. Never report a check that was not run.

## T3 preview tools

- `preview_open` with `target: {kind: "environment-port", port}` opens the dev server; pass `reuseExistingTab: false` and keep the returned `tabId`, since other agents may have tabs open.
- `preview_snapshot` reads the page, its elements and diagnostics. `preview_act` clicks, types, selects and scrolls. `preview_wait_for` waits for content. `preview_evaluate` reads values such as console errors.
- `preview_resize` checks a narrow and a wide viewport when layout changed. `preview_set_appearance` checks light and dark when colors changed.
- `preview_recording_start` and `preview_recording_stop` record a flow that a still image cannot show.
- Start servers on a free port: other worktrees may be running the same app. Stop the servers and close the tabs you opened when done.

## Screenshots of visual changes

A change is visual when it alters what a user sees: components, pages, styles, layout, copy, images, or a criterion that describes visible behavior. Set `visualChange` accordingly in the report; when unsure, treat it as visual.

For a visual change:

1. Capture the **after** state of every changed screen or state with `preview_snapshot` and `save: true`, which returns `screenshotPath`.
2. Capture the **before** state where it is cheap: take it before editing, or from the base commit. A new screen has no before.
3. Copy the files to the evidence directory named in the prompt, with descriptive names: `AC-2-profile-after.png`, `AC-2-profile-before.png`, `login-error-mobile-after.png`.
4. List every file in the report's `evidence` with its label and criterion.

Capture the state that proves the criterion, such as the filled form, the error message or the empty list, not just the page after loading. Do not include secrets or real personal data in a screenshot.

## What the lead does with the evidence

- `state.py impl` copies the listed files into the run directory. A visual change with no screenshot does not pass the gate.
- If the implementer could not use the preview tools, the lead starts the app from the implementer's worktree without editing it, captures the screenshots itself and records them with `state.py evidence`.
- The reviewer receives the paths, looks at the images and may repeat the walkthrough in its own worktree.
- The final report embeds each screenshot as `![label](/absolute/path.png)` so the user sees it in the T3 Code thread, and the PR shows the same images: see [publishing.md](publishing.md).
