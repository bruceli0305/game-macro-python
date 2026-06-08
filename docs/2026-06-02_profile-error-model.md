# Progress

## Goal

Move the Profile persistence and IPC path away from bare `String` errors and into the unified Rust error model.

## Done

- Added TOML serialize/deserialize variants to `AppError`.
- Added serializable `CommandError` and `CommandResult<T>` for Tauri command boundaries.
- Changed `ProfileStore` methods to return `AppResult<T>`.
- Changed `profile_list`, `profile_load`, and `profile_save` to return `CommandResult<T>`.
- Added a regression test for invalid TOML returning a typed `AppError::TomlDeserialize`.

## Files Changed

- `src-tauri/src/error.rs`
- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/profile_cmd.rs`

## Root Cause / Key Decision

The store and profile commands were building user-facing error strings at each call site. The new path keeps domain failures typed internally and converts only once at the Tauri command boundary.

## Logs / Tests

- `cargo test` passed: 64 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.

## Risks

- Tauri rejected invoke calls now return an object with `code` and `message`, not a plain string, for Profile commands.
- Other command modules still return `Result<_, String>` and should be migrated incrementally.

## Next Step

Migrate capture and skill import commands to `CommandResult<T>`, then move engine commands after the runtime control path is cleaned up.
