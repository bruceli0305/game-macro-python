# Progress

## Goal

Continue migrating Tauri command errors from bare `String` values to the unified command error model.

## Done

- Changed capture commands to return `CommandResult<T>`.
- Mapped capture sampling failures to `AppError::Capture`.
- Mapped enigo cursor failures to `AppError::Input`.
- Changed GW2 skill import command to return `CommandResult<T>`.
- Moved skill search implementation into an internal `AppResult<T>` helper.
- Mapped missing skill asset files to `AppError::Config`.
- Added unit coverage for GW2 fact parsing.

## Files Changed

- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/commands/skill_cmd.rs`

## Root Cause / Key Decision

Capture and skill import commands were still constructing ad hoc string errors. The migration keeps command success payloads unchanged and standardizes only the rejected error payload.

## Logs / Tests

- `cargo test` passed: 66 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.

## Risks

- Rejected capture and skill import invocations now return `{ code, message }` objects instead of plain strings.
- Engine commands still return `Result<_, String>` and should be migrated separately.

## Next Step

Migrate engine command errors after cleaning up the runtime control surface, especially engine start/stop state ownership and simulation serialization.
