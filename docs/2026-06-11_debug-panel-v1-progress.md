# Progress

## Goal

Implement V1 of the always-on-top loop debug panel: open a compact debug window, run a selected phase range once, and display structured key-attempt logs.

## Done

- Added backend debug task ownership separate from the normal engine task.
- Added one-shot debug runner using the existing `CycleExecutor` path.
- Added debug IPC commands:
  - `open_debug_panel_window`
  - `debug_run_once`
  - `debug_stop_run`
- Added structured debug events:
  - `debug:run-started`
  - `debug:run-event`
  - `debug:run-finished`
  - `debug:run-stopped`
  - `debug:run-failed`
- Added `/debug-panel` frontend route and compact `DebugPanelPage.vue`.
- Added `useDebugRun.ts` composable and debug run TypeScript event types.
- Added a small `调试面板` entry button to the engine control bar.
- Opened the Tauri debug window through `index.html?debugPanel=1` so production builds load the SPA entry reliably before routing to `/debug-panel`.
- Skipped global hotkey setup in the debug panel route to avoid duplicate registration from the secondary window.

## Files Changed

- `src-tauri/src/debug_task.rs`
- `src-tauri/src/engine/debug_runner.rs`
- `src-tauri/src/commands/debug_cmd.rs`
- `src-tauri/src/lib.rs`
- `src-tauri/src/commands/mod.rs`
- `src-tauri/src/engine/mod.rs`
- `src/types/debug-run.ts`
- `src/composables/useDebugRun.ts`
- `src/views/DebugPanelPage.vue`
- `src/router/index.ts`
- `src/App.vue`
- `src/components/engine/EngineControlBar.vue`
- `src/__tests__/debug-run-composable.test.ts`

## Root Cause / Key Decision

The debug panel needs to be visible over the game and must not mutate or reuse the normal engine task lifecycle. V1 therefore uses a separate always-on-top Tauri window and a separate debug task registry while still executing through the same `CycleExecutor` and key sender path as normal runtime.

## Logs / Tests

- `cargo fmt`
- `cargo test` - 199 tests passed.
- `cargo clippy --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test` - 18 files, 77 tests passed.
- `pnpm.cmd build`
- Manual dev smoke: `http://127.0.0.1:1420/debug-panel` returned HTTP 200.

## Risks

- V1 logs the execution result per attempt and key metadata, but does not yet expose every internal `AttemptEvent` as an individual row.
- V1 stops selected ranges using phase range boundaries and phase completion logs. Profiles with `fallback:stay` are treated as completed once the selected end phase completes.
- Real always-on-top behavior requires running in Tauri, not a browser-only dev page.

## Next Step

Use the panel against a real profile and decide whether V1 needs per-attempt-event rows, dry-run mode, or a pixel/condition inspection subpanel before adding loop or step modes.
