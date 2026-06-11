# Progress

## Goal

Refactor the remaining P1 issues instead of applying narrow patches:

- Bundled GW2 skill data lookup must work outside the development cwd.
- Engine start/stop must not race through the pending startup window.
- Frontend running state must not override backend failure events.
- Profile load must not replace corrupt or unreadable user data with defaults.
- IPC command files should stop owning domain-level validation and resource loading.

## Done

- Added `src-tauri/src/gw2/skills.rs` and reduced `skill_cmd.rs` to an IPC wrapper.
- Added `bundle.resources` for `assets/gw2/skills_all.json` in `tauri.conf.json`.
- Rewrote invalid/corrupt Tauri product/title strings to stable ASCII values.
- Added `src-tauri/src/engine_task.rs` with reservation, generation, gated install, cancellation, and stale-reservation tests.
- Moved profile semantic validation from `commands/profile_cmd.rs` to `profile/validation.rs`.
- Updated `engine_cmd.rs` to use the new task registry and profile validation module.
- Changed `useEngine.start()` so backend events/runtime snapshots are the source of truth for running state.
- Changed `useProfile.loadOrCreateProfile()` to create defaults only for explicit `Profile not found` errors.
- Added frontend regression tests for engine running state and profile load error handling.

## Files Changed

- `src-tauri/tauri.conf.json`
- `src-tauri/src/lib.rs`
- `src-tauri/src/engine_task.rs`
- `src-tauri/src/gw2/mod.rs`
- `src-tauri/src/gw2/skills.rs`
- `src-tauri/src/profile/mod.rs`
- `src-tauri/src/profile/validation.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/commands/skill_cmd.rs`
- `src/composables/useEngine.ts`
- `src/composables/useProfile.ts`
- `src/__tests__/composables-regression.test.ts`

## Tests

- `cargo test --manifest-path src-tauri\Cargo.toml`
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`
- `cargo fmt --manifest-path src-tauri\Cargo.toml --check`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`

## Risks

- `pnpm build` still reports the known large main chunk warning.
- Full installer packaging was not run; `cargo test` compiled the Tauri context and validates the config/resource syntax path.

## Next Step

Continue with medium-priority structural work: split `CycleExecutor`, split `CycleEditorPage.vue`, and code-split heavy frontend dependencies.
