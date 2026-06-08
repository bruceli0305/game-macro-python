# Progress

## Goal

Finish migrating Tauri command and store return types from bare Rust `Result<_, String>` to the unified `AppResult` / `CommandResult` model.

## Done

- Rewrote `engine_cmd.rs` with ASCII comments and unified command error returns.
- Changed `engine_start`, `engine_stop`, `simulate_rotation`, and `engine_status` to return `CommandResult<T>`.
- Changed engine profile loading helpers to return `AppResult<T>`.
- Fixed engine start state ownership: startup now checks state, loads profile config, then reserves the cancellation token.
- Added helper tests for engine cancellation token ownership.
- Verified `src-tauri/src/commands` and `src-tauri/src/store` no longer expose raw `-> Result` return types.

## Files Changed

- `src-tauri/src/commands/engine_cmd.rs`

## Root Cause / Key Decision

Engine commands were the final command layer still returning ad hoc string errors. `engine_start` also wrote its cancellation token before profile loading, so a configuration load failure could leave engine state looking occupied. The command now reserves runtime state only after configuration is loaded.

## Logs / Tests

- `cargo test` passed: 68 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.

## Risks

- Rejected engine invocations now return `{ code, message }` objects instead of plain strings.
- The engine loop still runs on a standard thread with blocking sleep; runtime async cleanup remains a separate task.

## Next Step

Move from error-model cleanup to runtime cleanup: replace the thread/sleep engine loop with a tokio task and explicit engine runtime handle ownership.
