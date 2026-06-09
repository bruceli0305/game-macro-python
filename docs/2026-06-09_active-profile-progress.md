# Progress

## Goal

Implement multi-role Profile switching through an active Profile selection.

## Done

- Added `settings.toml` under the app data root to persist `active_profile`.
- Added backend commands:
  - `profile_get_active`
  - `profile_set_active`
- Changed engine start, engine preflight, simulation, and capture pick config loading to use the active Profile.
- Added a sidebar Profile selector.
- Added Profile creation from either an empty default Profile or a copy of the current Profile.
- Changed Settings, Skills, Points, Cycle Editor, Simulator, and global hotkeys to load/save the active Profile.
- Added non-Tauri browser fallback for Profile composable calls so Vite-only development does not fail on missing IPC.

## Files Changed

- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/lib.rs`
- `src/components/AppLayout.vue`
- `src/composables/useProfile.ts`
- `src/composables/useEnginePreflight.ts`
- `src/composables/useHotkeys.ts`
- `src/stores/profile.ts`
- `src/views/SettingsPage.vue`
- `src/views/SkillsPage.vue`
- `src/views/PointsPage.vue`
- `src/views/CycleEditorPage.vue`
- `src/views/SimulatorPage.vue`

## Root Cause / Key Decision

The project already persisted multiple Profile directories, but runtime and UI paths were hardcoded to `default`.

The chosen boundary is:

```text
active Profile = base + skills + points + first rotation + state_schema
```

The engine still runs the first rotation of the active Profile. Multi-rotation editing is intentionally left out.

Profile directory IDs are restricted to ASCII letters, numbers, `_`, and `-` to avoid path traversal and cross-platform filename problems. User-facing names can be handled later through `meta.profile_name`.

## Logs / Tests

- `cargo fmt --manifest-path src-tauri\Cargo.toml`
- `cargo test --manifest-path src-tauri\Cargo.toml`
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`
- Browser check on `http://127.0.0.1:1420/settings`:
  - Profile selector is visible.
  - Create Profile modal opens.
  - Vite-only fallback can create and switch to a test Profile in memory.

## Risks

- Existing real app data may still contain only `profiles/default/profile.toml`; this remains valid and becomes the default active Profile.
- If a user manually edits `settings.toml` to an invalid Profile ID, active Profile loading returns a validation error.
- Profile delete/rename is not implemented yet.

## Next Step

Add observer/action slots for condition-only runtime actions, then map `急速燃.a2` without fake zero-count skills.
