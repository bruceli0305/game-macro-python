# Progress

## Goal

Tighten the first set of project-level cleanup items from the repository walkthrough without touching the broader migration worktree state.

## Done

- Replaced mojibake runtime reason strings in `CycleExecutor` with stable ASCII reason codes.
- Removed a library-code `unwrap()` from skill readiness checks.
- Moved GW2 skill search IPC out of `Gw2ImportDialog.vue` into a dedicated `useSkill` composable.
- Removed the broad `unused_imports` crate allowance and fixed the exposed unused import.
- Kept a narrower `dead_code` crate allowance because many migration skeleton modules are intentionally present but not fully wired yet.

## Files Changed

- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/lib.rs`
- `src/composables/useSkill.ts`
- `src/components/editor/Gw2ImportDialog.vue`
- `docs/2026-06-08_project-boundary-cleanup.md`

## Root Cause / Key Decision

The repository already builds, but a few issues violated the project boundaries or made maintenance harder. The direct Tauri call in a component bypassed the composable layer, and the executor had user-visible corrupted reason text plus a library `unwrap()`. Removing all `dead_code` allowance exposed broad planned-but-unwired migration code, so this pass narrowed the allowance instead of doing unrelated deletion.

## Logs / Tests

- `cargo fmt`
- `cargo test` passed: 76 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed as part of `pnpm.cmd build`.
- `pnpm.cmd test` passed: 2 files, 3 tests.
- `pnpm.cmd build` passed.

## Risks

- The v2 migration files are still mostly untracked, so `git diff` does not show this pass until the migration tree is added to Git.
- `#![allow(dead_code)]` remains at crate level as a migration-period compromise.
- Other modules may still contain non-runtime mojibake comments, but the executor path cleaned in this pass no longer has the searched mojibake markers.

## Next Step

Decide the Git migration boundary: either add the v2 tree as the current baseline, or split the old Python move and the Tauri/Vue/Rust implementation into separate commits before continuing deeper cleanup.
