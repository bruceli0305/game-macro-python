# Progress

## Goal

Complete the agreed 1-5 follow-up plan for the Tauri/Vue/Rust rewrite:

1. Initialize and validate the default profile before engine startup.
2. Connect `SettingsPage` to the real profile configuration.
3. Wire `CycleEditor` point options and save-time reference validation.
4. Implement per-skill cooldown, ammo, and `shots_per_cycle` scheduling.
5. Polish UI display and runtime log labels.

## Done

- Added default profile creation through `ProfileStore::load_or_create_default`.
- Added profile reference validation before saving profiles.
- Added engine startup validation for executable rotations and trigger keys.
- Mapped base execution settings into `SkillAttemptConfig`.
- Added cycle scheduling checks for per-skill cooldown, ammo pixels, and shots per cycle.
- Connected settings UI to the persisted profile base config.
- Connected cycle editor slot dialogs to saved point options.
- Improved skill cards with key, timing, and condition metadata.
- Added localized attempt failure labels in the execution log viewer.
- Registered Naive UI providers in `App.vue` so page-level message APIs have the required context.

## Files Changed

- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src/views/SettingsPage.vue`
- `src/views/CycleEditorPage.vue`
- `src/App.vue`
- `src/components/editor/PhaseLane.vue`
- `src/components/editor/SkillCard.vue`
- `src/components/engine/ExecLogViewer.vue`

## Root Cause / Key Decision

The project had the core Rust modules and front-end shell in place, but the app still lacked a persisted default profile path and the engine could start from an invalid or non-executable configuration. The fix keeps validation in command/service boundaries, keeps models passive, and makes the UI consume the same profile data that the engine uses.

For scheduling, cooldown and ammo decisions belong in `CycleExecutor`, because that is where phase progression and slot readiness are evaluated. The implementation tracks fired counts per cycle and skill ready timestamps without moving business rules into UI or model structs.

## Logs / Tests

- `cargo fmt`
- `cargo test`
- `cargo clippy --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`
- Browser smoke check for `/settings` and `/cycle-editor` through the local Vite server.

## Risks

- Browser-only Vite checks cannot fully exercise Tauri IPC commands; full desktop validation should still be done through `pnpm tauri dev` before release.
- The current ammo detection supports configured stage pixels, but real-game tuning still depends on reliable point calibration.

## Next Step

Run the app through Tauri, create a real profile with points and skills, then perform a manual engine start/stop smoke test against a non-game target window before any GW2-specific use.
