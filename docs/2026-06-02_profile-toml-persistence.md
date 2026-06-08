# Progress

## Goal

Align Profile persistence with the project contract: backend storage uses TOML while frontend IPC continues to exchange JSON payloads.

## Done

- Changed `ProfileStore` to persist `profile.toml`.
- Kept `profile_load` / `profile_save` IPC payloads as JSON strings, so frontend call sites do not need protocol changes.
- Added a store regression check that `profile.toml` is created and `profile.json` is not created.
- Updated cycle editor design notes to describe TOML backend persistence.

## Files Changed

- `src-tauri/src/store/profile_store.rs`
- `docs/CYCLE_EDITOR_DESIGN.md`
- `docs/2026-06-02_profile-boundary-baseline.md`

## Root Cause / Key Decision

The code stored Profiles as JSON while the project guidance specified human-readable TOML persistence. The least disruptive correction is to keep JSON as the IPC serialization format and move only the file store to TOML.

## Logs / Tests

- `cargo test` passed: 63 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.

## Risks

- Existing local `profile.json` files will not be loaded by the new store.
- The repository is still in a broad migration worktree where v2 files are mostly untracked.

## Next Step

Introduce a typed Rust error path for store and command failures, replacing `Result<_, String>` with the existing unified error model.
