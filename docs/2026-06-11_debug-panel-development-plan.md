# Loop Debug Panel Development Plan

## Goal

Implement V1 of the loop debug panel as an always-on-top Tauri window that can run a selected phase range once and show detailed key-attempt diagnostics.

## Phase 1: Contracts and Data Model

- Define debug run request type:
  - `start_phase_index`
  - `end_phase_index`
- Define debug run state:
  - idle
  - running
  - completed
  - failed
  - stopped
- Define event payloads:
  - started
  - event
  - finished
  - stopped
  - failed
- Decide exact event names:
  - `debug:run-started`
  - `debug:run-event`
  - `debug:run-finished`
  - `debug:run-stopped`
  - `debug:run-failed`

Deliverable:

- Rust payload structs.
- TypeScript payload interfaces.

## Phase 2: Tauri Window Command

- Add `open_debug_panel_window`.
- Use window label `debug-panel`.
- If existing: show and focus.
- If missing: create a new always-on-top window routed to `/debug-panel`.
- Use default size around `420 x 560`.

Deliverable:

- Main app can open the debug panel window.
- Repeated open attempts do not create duplicate windows.

## Phase 3: Backend One-Shot Debug Runner

- Add a debug task state holder.
- Add `debug_run_once`.
- Add `debug_stop_run`.
- Load active profile using existing profile config path.
- Reject invalid phase ranges.
- Reject when normal engine is running.
- Reject when a debug task is already running.
- Construct an independent `CycleExecutor`.
- Run from start phase through end phase once.
- Emit structured debug events.
- Apply max duration / max tick protection.

Deliverable:

- `P1 -> P1` and `P1 -> P2` can run once from IPC.
- Logs include phase, skill, key, outcome, and reason.

## Phase 4: Frontend Debug Composable

- Add `useDebugRun.ts`.
- Encapsulate all debug IPC and Tauri event listeners.
- Track:
  - status
  - current run id
  - elapsed time
  - current phase
  - logs
  - latest error
- Provide actions:
  - `runOnce`
  - `stop`
  - `clearLogs`

Deliverable:

- Debug UI can use one composable without direct `invoke()` or `listen()` calls.

## Phase 5: Debug Panel Page

- Add route `/debug-panel`.
- Add `DebugPanelPage.vue`.
- Build compact UI:
  - title / always-on-top indicator
  - phase range selects
  - run / stop / clear controls
  - current run summary
  - log list
- Keep the page independent from `CycleEditorPage.vue`.

Deliverable:

- Always-on-top window shows usable debug controls and live logs.

## Phase 6: Main Window Entry

- Add a small `Debug Panel` button in the existing editor or engine control surface.
- Button invokes `open_debug_panel_window` through a composable or existing IPC wrapper.
- Do not embed debug logs into the main page.

Deliverable:

- User can open the debug panel from the main app.

## Phase 7: Tests

### Rust

- Range validation rejects `start > end`.
- Range validation rejects out-of-range phase indices.
- Normal engine running rejects debug run.
- Debug run already running rejects another run.
- Single phase run finishes without entering next phase.
- Continuous phase run stops at selected end phase.
- Debug event contains phase, skill, key, outcome, and reason.

### Frontend

- `useDebugRun` transitions idle -> running -> completed.
- `useDebugRun` records failed state.
- `useDebugRun` appends log events.
- `DebugPanelPage` disables run button while running.
- Phase range selection prevents invalid ranges.

### Verification Commands

- `cargo fmt`
- `cargo test`
- `cargo clippy --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`

## Phase 8: V1 Completion Criteria

- The debug panel opens as an always-on-top independent window.
- The user can run `P1 -> P1` once.
- The user can run a continuous range like `P1 -> P2` once.
- The log clearly shows successful key sends, skips, failures, and reasons.
- The normal engine and debug run cannot run concurrently.
- The implementation keeps command, engine, composable, and view boundaries clean.

## Deferred Work

- Loop run mode.
- Step mode.
- Breakpoints.
- Condition tree expansion.
- Pixel sample inspector.
- Runtime state inspector.
- Log export.
- Persisted window position and size.
