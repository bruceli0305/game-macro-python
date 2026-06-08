# Progress

## Goal

Advance the next development phase across configuration closure, capture usability, skill management, engine-safe startup, and simulator/debugging support.

## Done

- Imported the global Tailwind/style entry from `src/main.ts`, restoring app-wide layout utilities.
- Added global dark scrollbar styling in `src/style.css`.
- Expanded scrollbar styling across native scroll containers and Naive UI scrollbar rails:
  - stable dark track/thumb colors for Chromium/WebKit and Firefox.
  - rounded hover/active states and hidden native scrollbar buttons.
  - fixed Naive vertical/horizontal rail thickness for dense editor panels and tables.
- Reworked the cycle editor into a stable two-column desktop workspace with scoped layout CSS.
- Improved phase lanes with stable headers, empty states, and horizontal skill rows.
- Improved skill cards with fixed dimensions plus explicit edit/delete icon actions.
- Added front-end profile validation utilities:
  - save-time reference validation for missing skill and point references.
  - run-time executable validation for empty rotations, empty phases, unselected skills, disabled-only cycles, and missing trigger keys.
- Added validation regression tests.
- Wired save-time validation and user messages into skills, points, and cycle editor pages.
- Wired run-time validation into engine start and offline simulator execution.
- Shared the engine start preflight between the visible start button and the global F9 hotkey.
- Added a global app-message bridge so hotkey-triggered validation errors are visible through Naive UI messages.
- Made global hotkey registration configuration-driven:
  - `base.pick.confirm_hotkey` controls the capture confirmation shortcut.
  - `base.exec.toggle_hotkey` controls the engine toggle shortcut.
  - empty legacy values fall back to visible F8/F9 defaults.
- Settings saves now trigger an in-app hotkey reload, so changed shortcuts take effect without restarting the desktop app.
- Exposed the capture confirmation hotkey on the settings page.
- Added save-time validation that rejects conflicting capture and engine hotkeys in both the frontend and backend.
- Added a real engine-start safety gate for `base.exec.enabled`: visible start button, F9 hotkey, and backend `engine_start` reject startup when macro execution is disabled, while offline simulator commands remain usable.
- Tightened save-time profile invariants in both frontend and backend:
  - skills must have non-empty names.
  - skill pixels and ammo-stage pixels must have a monitor and a supported sample mode.
  - points must have non-empty names, monitors, valid sample modes, and valid pixel fields before persistence.
  - base timing and safety settings must stay within UI-supported ranges before persistence.
  - cast-bar mode must be explicit (`timer` or `pixel`), and rotation polling cannot be zero.
- Added a reusable profile issue summary:
  - cycle editor now shows a full engine-start issue summary next to the run controls.
  - simulator now shows a run-readiness issue summary before offline execution.
  - settings now reuses the same save-readiness summary when the edited base config or existing profile has blocking issues.
  - first-error message gating remains in place for save/start/run actions.
- Tightened settings editing UX:
  - cast-bar mode is now selected from explicit `timer` / `pixel` options instead of free text.
- Removed unnecessary `NLog` language highlighting to avoid the Naive UI `hljs is not set` console error source.
- Added ammo-stage editing in the skill editor, including per-stage charges, pixel coordinates, tolerance, color, and F8 capture.
- Added immediate skill draft validation in the skill editor:
  - visible/editable skill ID field.
  - rejects empty ID/name, duplicate IDs, enabled skills without trigger keys, and duplicate ammo-stage charges before adding the draft to the list.
  - normalizes skill ID/name/trigger key and monitor fields before saving the draft.
- Added save-time validation for duplicate ammo-stage charge counts.
- Added backend save-time validation for duplicate skill IDs, duplicate point IDs, cast-bar point references, empty IDs, and duplicate ammo-stage charge counts.
- Added `simulate_rotation_with_pixels` so the simulator can run with explicit pixel samples instead of the real screen.
- Added simulator pixel-state controls for points, skill pixels, and ammo stages.
- Capture commands now resolve the monitor from absolute cursor coordinates instead of assuming `primary`.
- `capture_at_cursor` now honors `base.pick.mouse_avoid`, `mouse_avoid_offset_y`, and `mouse_avoid_settle_ms`: it records the original cursor position, optionally moves the cursor away before sampling, waits for the configured settle time, samples the original pixel, and then attempts to restore the cursor.
- Captured points, skill pixels, and ammo-stage pixels now persist the actual monitor returned by the backend.
- Added immediate point draft validation and normalization:
  - captured points are normalized before being added to the table.
  - point saves reject empty IDs/names, duplicate IDs, invalid coordinates, RGB values, tolerance, and sample radius before profile persistence.
  - point ID and tolerance are editable from the point table so captured samples can be turned into stable references without editing TOML by hand.
- Added a Rust regression test proving pixel overrides can satisfy simulator point conditions.
- Reworked `PixelPreview` to use the capture composable instead of direct Tauri invocation and random sample coordinates.
- Exposed monitor columns and fields in point and skill management so multi-monitor captures can be audited from the UI.
- Verified `pnpm tauri dev` launches the desktop app after freeing port 1420.
- Confirmed the Tauri window is responsive with title `激战2 协同学院 自动化克鲁`.
- Confirmed the desktop profile path exists at `%LOCALAPPDATA%\game-macro-tauri\profiles\default\profile.toml`.
- Simulator events now include executor log event type and reason, including skipped skills.
- Added simulator reason display so condition failures, ammo misses, cooldowns, and other skip causes are visible in the UI.
- Added simulator debug summary and export support:
  - event/executed/skipped/success/not-ready/failure/duration summary cards.
  - top reason tags for quick diagnosis.
  - copyable debug JSON containing generated timestamp, summary, and raw events.
  - clear-results action for repeated simulator runs.
- Added a Rust regression test proving simulator pixel mismatches report `NOT_READY` with a condition reason.
- Added a desktop IPC smoke-test utility for simulator debugging:
  - checks default profile loading.
  - runs save-level profile validation.
  - skips simulator IPC when run-readiness validation fails.
  - runs both `simulate_rotation` and `simulate_rotation_with_pixels` when the profile is executable.
- Added a simulator-page `IPC 自检` action and result panel so desktop click-through can verify the simulator IPC path without starting the real macro engine or sending keys.
- Added profile-payload simulator IPC commands:
  - `simulate_profile_rotation`
  - `simulate_profile_rotation_with_pixels`
  - both run through the existing simulator executor with `NoopKeySender`, so they do not start the real engine or send keys.
- Added an in-memory IPC smoke fixture profile with one point, one enabled skill, and one pixel-gated phase.
- Added a backend-owned IPC smoke fixture command:
  - `simulate_ipc_smoke_fixture`
  - direct simulation uses a no-condition fixture so it does not depend on screen capture contents.
  - pixel simulation uses a point condition plus explicit pixel overrides.
  - returns event-count summary for the simulator page self-check.
- Extended the simulator IPC smoke flow:
  - default-profile checks still show whether the saved user config is runnable.
  - fixture-profile checks can exercise the full simulator IPC path in the Tauri runtime without overwriting the user's default profile.
  - backend fixture checks can prove the Rust-side no-key simulator path independently of frontend profile construction.
  - non-Tauri browser runs mark fixture IPC steps as skipped instead of failed.
- Added regression tests for the IPC smoke-test control flow and the profile-payload simulator commands.
- Added a capture diagnostics IPC command:
  - `capture_diagnostics`
  - enumerates monitors.
  - reads current cursor position.
  - resolves the cursor monitor.
  - attempts one screen sample at the cursor and returns either the sampled color or a sample error.
- Added a `取色诊断` action on the points page. It does not create or save points; it only displays diagnostics so desktop validation can separate runtime availability, monitor resolution, cursor location, and sampling failures.
- Added point-capture handling counters on the points page:
  - request/success/failure/ignored counts are updated when the page receives the `picker:capture` event.
  - this makes the F8 desktop callback smoke test observable beyond toast messages.
- Reused the same capture handling counters in the skill editor:
  - skill-pixel capture and ammo-stage capture record request/success/failure/ignored counts.
  - the editor modal displays the latest capture context so desktop validation can distinguish skill and ammo capture handling.
- Added a picker-store regression test for capture request/success/failure/ignored counters and last-context state.

- Added an engine preflight IPC command:
  - `engine_preflight`
  - loads the saved default profile from disk.
  - reports execution enablement, profile/rotation/skill/point counts, executable slot count, current engine-running state, and the blocking error when startup is not ready.
- Added a backend preflight action to the engine control bar so the visible UI can verify the backend startup gate separately from the frontend profile issue summary.
- Extended the simulator IPC self-check with a backend engine-preflight row:
  - browser/Vite runs mark it as skipped when Tauri IPC is unavailable.
  - Tauri runs call `engine_preflight` and display the returned `ready` state plus the blocking reason without starting the macro engine.
- Extended the simulator IPC self-check with a non-mutating capture diagnostics row:
  - browser/Vite runs mark it as skipped when Tauri IPC is unavailable.
  - Tauri runs call `capture_diagnostics`, reports cursor monitor/position and the sampled color or capture error, and does not create or save points.
- Extended the simulator IPC self-check with a global-hotkey registration diagnostics row:
  - browser/Vite runs mark it as skipped when Tauri IPC is unavailable.
  - Tauri runs load the configured F8/F9-equivalent hotkeys and checks whether both are registered through the global-shortcut plugin.
  - hotkey callbacks now record trigger counts and last-trigger timestamps, so pressing F8/F9 in the desktop window can be confirmed by re-running the self-check.
  - this proves registration state but does not replace the final manual F8/F9 callback smoke test.
- Extended the simulator IPC self-check with a profile JSON round-trip row:
  - runs in memory only and does not write the profile back to disk.
  - serializes the loaded profile and parses it back to confirm the frontend shape preserves profile identity and section counts.
- Added a copyable simulator IPC self-check report:
  - exports generated timestamp, passed/failed/skipped counts, and all self-check step details as JSON.
  - intended for recording the real Tauri-window validation result after running the self-check in the desktop app.
- Added regression tests for backend preflight reports covering empty default profiles, executable profiles, and already-running engine state.

## Files Changed

- `src/main.ts`
- `src/style.css`
- `src/utils/profile-validation.ts`
- `src/__tests__/profile-validation.test.ts`
- `src/views/CycleEditorPage.vue`
- `src/views/SkillsPage.vue`
- `src/views/PointsPage.vue`
- `src/views/SimulatorPage.vue`
- `src/components/editor/PhaseLane.vue`
- `src/components/editor/SkillCard.vue`
- `src/components/engine/EngineControlBar.vue`
- `src/components/engine/ExecLogViewer.vue`
- `src/components/picker/PixelPreview.vue`
- `src/composables/useCapture.ts`
- `src/composables/useEngine.ts`
- `src/composables/useEnginePreflight.ts`
- `src/composables/useHotkeys.ts`
- `src/components/AppLayout.vue`
- `src/App.vue`
- `src/views/SettingsPage.vue`
- `src/__tests__/hotkey-validation.test.ts`
- `src/__tests__/engine-start-validation.test.ts`
- `src/__tests__/skill-validation.test.ts`
- `src/__tests__/point-validation.test.ts`
- `src/__tests__/simulation-debug.test.ts`
- `src/__tests__/profile-issue-summary.test.ts`
- `src/utils/skill-validation.ts`
- `src/utils/point-validation.ts`
- `src/utils/profile-issue-summary.ts`
- `src/utils/simulation-debug.ts`
- `src/utils/desktop-ipc-smoke.ts`
- `src/utils/ipc-smoke-profile.ts`
- `src/components/common/ProfileIssueSummary.vue`
- `src/__tests__/desktop-ipc-smoke.test.ts`
- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/lib.rs`

## Root Cause / Key Decision

The UI could not reliably support configuration because the global stylesheet was not imported, so utility layout classes did not exist at runtime. The cycle editor also mixed editing, runtime status, and logs in a single vertical flow. The fix restores global CSS and gives the editor explicit scoped CSS for critical layout so the page remains usable even if utility generation changes.

The configuration workflow also lacked early, user-visible validation. Backend validation already protected part of persistence and engine startup, but it did not fully match the new UI-level checks. The front-end validation now provides immediate feedback, while `profile_save` enforces the same save-level invariants for malformed direct IPC payloads.

## Logs / Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test` (39 tests)
- `pnpm.cmd build`
- `cargo fmt`
- `cargo test` (110 tests)
- `cargo clippy --all-targets -- -D warnings`
- Browser smoke checks for:
  - `/cycle-editor`
  - `/cycle-editor` scrollbar CSS computed styles, Naive rail sizing, and horizontal-overflow check
  - `/cycle-editor` start issue summary
  - `/cycle-editor` backend preflight button in browser mode: skipped with `Tauri IPC runtime unavailable`
  - `/skills`
  - `/points`
  - `/simulator`
  - `/simulator` run issue summary
  - skill editor ammo-stage controls
  - skill editor ID field in the modal
  - skill editor skill-pixel/ammo-stage capture handling counters and waiting-state panel
  - simulator pixel-state controls
  - simulator copy/clear debug controls
  - point and skill monitor columns
  - point table ID/tolerance columns
  - points page capture diagnostics button and non-Tauri skip panel
  - points page point-capture handling counters
  - simulator event and reason columns
  - simulator IPC self-check button and result panel
  - simulator IPC self-check copyable JSON report button
  - simulator IPC self-check empty-profile path: profile load/save validation pass, simulator IPC steps skipped by run-readiness validation
  - simulator IPC self-check profile JSON round-trip row in browser mode: passed without writing profile data
  - simulator IPC self-check backend engine-preflight row in browser mode: skipped with `Tauri IPC runtime unavailable`
  - simulator IPC self-check capture diagnostics row in browser mode: skipped with `Tauri IPC runtime unavailable`
  - simulator IPC self-check hotkey registration row in browser mode: skipped with `Tauri IPC runtime unavailable`
  - simulator IPC self-check fixture rows in browser mode: fixture validates, IPC steps are skipped with `Tauri IPC runtime unavailable`
  - simulator IPC self-check backend fixture row in browser mode: skipped with `Tauri IPC runtime unavailable`
  - App layout after adding the global message bridge
  - settings page capture-hotkey field
  - settings page after hotkey-reload wiring
  - settings page after base-config validation wiring
  - settings page save-readiness summary wiring and cast-bar mode select
- Tauri desktop launch smoke:
  - `pnpm tauri dev`
  - Vite ready at `http://localhost:1420`
  - Rust dev build finished
  - `game-macro-tauri.exe` running and responding
  - default profile TOML present under `%LOCALAPPDATA%\game-macro-tauri`

## Risks

- Browser checks are still Vite-level checks; the desktop app now launches, but IPC workflows still need in-window click-through validation.
- The capture workflow now has a non-mutating diagnostics panel and point-capture handling counters, but it still needs an in-window Tauri diagnostics pass plus an F8 capture test for cursor sampling and screen permissions.
- The simulator self-check now includes capture diagnostics, but browser coverage only verifies the skip path; real screen sampling still needs Tauri-window evidence.
- Backend engine preflight has Rust and browser skip-path coverage, but it still needs a real Tauri-window pass against the saved profile on disk.
- Hotkey registration and callback counts are now visible in the simulator self-check, but pressing F8/F9 still needs a real Tauri-window callback smoke test.
- Multi-monitor capture is now represented in saved data and visible in the UI, but it still needs real multi-monitor desktop validation.
- The simulator pixel-state controls generate target/mismatch RGB overrides, and the IPC self-check can exercise the full simulator IPC path through an in-memory fixture profile in the Tauri runtime; the browser smoke verifies the non-Tauri skip path only.
- Skill management has ammo-stage editing and browser-verified capture waiting-state feedback, but real F8 capture of each stage still needs desktop validation.
- Global F9 startup now uses the same preflight as the visible start button, but the actual global shortcut callback still needs desktop hotkey smoke validation.

## Next Step

Use the running Tauri window to click through profile save/load, points-page capture diagnostics, F8 point capture, skill editing, cycle save validation, engine preflight validation, simulator pixel-state execution, and the simulator IPC self-check fixture path until the two frontend fixture IPC rows and the backend fixture row pass.
