# Progress

## Goal

Remove the crate-level `dead_code` allowance and keep the post-migration workspace clean.

## Done

- Added `.reasonix/` to `.gitignore` so local tool output no longer appears as an untracked project change.
- Removed `#![allow(dead_code)]` from the Tauri library root.
- Made the established Rust layers public library modules so their public types are treated as reachable API instead of private dead code.
- Removed unused GW2 raw skill fields that were not part of the import behavior.
- Removed unused pending-attempt state and an unused test helper from Rust engine code.

## Files Changed

- `.gitignore`
- `src-tauri/src/lib.rs`
- `src-tauri/src/commands/skill_cmd.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/engine/skill_attempt.rs`
- `docs/2026-06-08_dead-code-boundary-cleanup.md`

## Root Cause / Key Decision

The earlier crate-level `dead_code` allowance was hiding broad warnings caused by public project modules being nested inside a private crate boundary. Publishing the stable internal layers as library modules removes that false positive without deleting migration-era code. The remaining warnings were real unused fields/helpers and were removed.

## Logs / Tests

- `cargo fmt`
- `cargo clippy --all-targets -- -D warnings` passed.
- `cargo test` passed: 76 tests.
- `pnpm.cmd build` passed before the final Rust-only cleanup; no frontend source changed after that build.

## Risks

- Public Rust module visibility is broader than before, but this crate is still the app backend library and the exposed layers match the documented architecture.
- The project still has future cleanup work in comments and unused feature skeletons, but they are no longer hidden by a crate-wide dead-code allowance.

## Next Step

Add focused integration coverage for the first-run profile flow so the app can create, save, reload, and execute a default profile path end to end.
