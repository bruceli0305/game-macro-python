# Progress

## Goal

Prepare the v2 codebase for follow-up development by tightening the Profile save path, removing direct Tauri IPC calls from views, and restoring the Rust lint baseline.

## Done

- Added shared Profile default construction and section merge helpers.
- Refactored Skills, Points, Cycle Editor, and Simulator pages to call composables instead of Tauri `invoke()`.
- Changed section saves so skills, points, and rotations preserve the other Profile sections.
- Fixed existing Rust clippy warnings without changing runtime behavior.
- Added frontend regression tests for Profile section updates.

## Files Changed

- `src/composables/useProfile.ts`
- `src/composables/useCapture.ts`
- `src/composables/useEngine.ts`
- `src/views/SkillsPage.vue`
- `src/views/PointsPage.vue`
- `src/views/CycleEditorPage.vue`
- `src/views/SimulatorPage.vue`
- `src/__tests__/profile-merge.test.ts`
- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/ast/evaluator.rs`
- `src-tauri/src/capture/capturer.rs`
- `src-tauri/src/capture/scanner.rs`
- `src-tauri/src/engine/skill_attempt.rs`
- `src-tauri/src/engine/cycle_executor.rs`

## Root Cause / Key Decision

The original pages rebuilt partial Profile objects locally. Saving one page could drop data owned by another page, especially Cycle Editor overwriting `points` with an empty array. The fix centralizes Profile loading and section updates in `useProfile`.

## Logs / Tests

- `pnpm.cmd exec vitest run` passed: 1 file, 2 tests.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `cargo test` passed: 63 tests.
- `cargo clippy --all-targets -- -D warnings` passed.

## Risks

- The repository is still in a large migration worktree where current v2 files are untracked.
- The persistence contract should be verified after the store is migrated to TOML.
- Tauri/Vite full build was not re-run in this step because the earlier sandbox build path hit esbuild spawn restrictions and one elevated build timed out.

## Next Step

Migrate `ProfileStore` to TOML persistence, keeping the frontend IPC payload as JSON.
