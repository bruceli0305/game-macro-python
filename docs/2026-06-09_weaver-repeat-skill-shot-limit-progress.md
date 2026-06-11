# Progress

## Goal
Fix Condition Weaver rotation stalls where repeated attunement and weapon skills stop firing after the first few successful keys.

## Done
- Changed cycle executor semantics so `shots_per_cycle = 0` means unlimited repeat attempts within the current cycle.
- Kept positive values as strict per-cycle limits.
- For `all_fired` phases, unlimited skills count as complete after they have fired in the current phase.
- Added a regression test for a loop that jumps between phases while reusing the same skill id without resetting the cycle.
- Added `default_shots_per_cycle = 0` to the Condition Weaver role seed.
- Updated the active local Condition Weaver profile so all 23 Weaver skills use `shots_per_cycle = 0`.
- Allowed the Skills page input to accept `0`.

## Files Changed
- `src-tauri/src/engine/cycle_executor.rs`
- `src/assets/json/role-profile-seeds.json`
- `src/utils/role-profile-templates.ts`
- `src/views/SkillsPage.vue`
- `src/__tests__/role-profile-templates.test.ts`
- `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`

## Root Cause / Key Decision
Condition Weaver uses repeated skill ids across the same long-running loop, especially `weaver_attune_earth`, `weaver_attune_fire`, `weaver_earth_pistol_2`, and `weaver_fire_pistol_2`.

The executor counted fired skills in `fired_count_in_cycle`, but the Weaver loop jumps from the final loop phase back to `Loop - Fire` instead of reaching the end of the phase list. That means the cycle counter did not reset and `shots_per_cycle = 1` blocked later repeated slots with `shots_per_cycle_exhausted=1`.

Using `0` as an explicit unlimited value is cleaner than raising the limit to an arbitrary large number.

## Logs / Tests
- `pnpm.cmd test -- src/__tests__/role-profile-templates.test.ts src/__tests__/cycle-presets.test.ts`: passed 70 tests.
- `cargo test --manifest-path src-tauri/Cargo.toml`: passed 180 tests.
- `cargo clippy --manifest-path src-tauri/Cargo.toml --no-default-features -- -D warnings`: passed.
- `pnpm.cmd build`: passed with existing Vite chunk size warning.
- `git diff --check`: passed with CRLF warnings only.

## Risks
- Existing user-created profiles that still have repeated loop skills with `shots_per_cycle = 1` can hit the same limiter. They should either set repeated skills to `0` or restructure the loop to reset the cycle.
- Runtime testing still requires restarting the desktop app so the updated executable and active profile are loaded.

## Next Step
Restart the desktop app, start the Condition Weaver profile, and watch for `shots_per_cycle_exhausted=1` in execution logs. That reason should no longer appear for Weaver skills in the updated active profile.
