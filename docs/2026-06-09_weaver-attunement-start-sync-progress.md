# Progress

## Goal
Fix Condition Weaver startup attunement routing so the rotation can enter the intended Earth/Earth opener from common unknown or non-Earth start states.

## Done
- Added an initial `Preparation - sync Earth primary` phase to the Condition Weaver cycle preset.
- The sync phase presses `weaver_attune_earth` only when the primary attunement is not Earth.
- The sync phase confirms only `attune_earth_primary`, then lets the existing preparation phase press Earth again when needed to reach Earth/Earth.
- Synced the active local profile at `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`.
- Added a preset regression assertion for the startup sync phase.

## Files Changed
- `src/assets/json/cycle-presets.json`
- `src/__tests__/cycle-presets.test.ts`
- `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`

## Root Cause / Key Decision
The previous first phase pressed Earth and immediately required the full Earth/Earth pair. With Weaver mechanics, pressing a new attunement changes primary to the pressed element and secondary to the previous primary. From Fire/Earth, one Earth press results in Earth/Fire, not Earth/Earth, so the first phase could only pass through timeout fallback and the actual attunement chain drifted.

The fix keeps pair-level confirmation for semantic phases, but adds a startup-only primary sync so the existing double-Earth opener becomes reachable.

## Logs / Tests
- Static attunement transition simulation: common starts now produce zero unreachable attunement targets.
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts`: passed 70 tests.
- `pnpm.cmd build`: passed, with existing Vite chunk size warning.
- `cargo test --manifest-path src-tauri/Cargo.toml`: passed 179 tests.
- `cargo clippy --manifest-path src-tauri/Cargo.toml --no-default-features -- -D warnings`: passed.
- `git diff --check`: passed, with CRLF warnings only.

## Risks
- Runtime testing still needs a fresh desktop app restart because the currently running process may have loaded the old profile in memory.
- The pair colors still depend on the sampled UI layout; if the game UI scale or skill bar moves, re-picking the attunement points is still required.

## Next Step
Restart the Tauri desktop app, load the Condition Weaver profile, and verify the first log entries show Earth primary sync before the Earth/Earth preparation phase.
