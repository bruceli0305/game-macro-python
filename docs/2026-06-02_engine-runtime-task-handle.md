# Progress

## Goal

Move the engine command runtime away from unmanaged OS thread spawning and toward explicit Tauri/tokio task ownership.

## Done

- Added `EngineTaskHandle` to hold the active engine cancellation token and Tauri async `JoinHandle`.
- Replaced `AppState.engine_cancel` with `AppState.engine_task`.
- Changed `engine_start` to reserve a pending task before loading profile config, preventing concurrent start races.
- Changed the engine loop from `std::thread::spawn` plus blocking `std::thread::sleep` to `tauri::async_runtime::spawn` plus cancellable `tokio::select!`.
- Kept `engine_stop` cooperative: it takes the stored task and cancels the token.
- Updated engine command state tests for task-handle semantics.

## Files Changed

- `src-tauri/src/lib.rs`
- `src-tauri/src/commands/engine_cmd.rs`

## Root Cause / Key Decision

The previous runtime state only stored a cancellation token. That made command status cheap, but the spawned engine loop itself was unmanaged and slept on an OS thread. The new handle makes task ownership explicit and lets the async runtime wake the loop immediately when cancellation is requested.

## Logs / Tests

- `cargo fmt`
- `cargo test` passed: 68 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.

## Risks

- `engine_stop` does not await task completion yet; shutdown is cooperative and completion is reported by the existing `engine:stopped` event.
- Input sending still has a small blocking sleep in `input/key_sender.rs` for key press timing. That is separate from the engine loop scheduling cleanup.

## Next Step

Wire runtime state metrics into engine log/status events so the frontend can display meaningful live execution state instead of only start/stop and tick snapshots.
