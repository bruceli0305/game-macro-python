# Progress

## Goal

Expose engine runtime metrics to the frontend so the cycle editor can show live skill execution state instead of only tick and log events.

## Done

- Added `engine:runtime` event payload in `engine_cmd.rs`.
- Added runtime payload mapping for engine status, phase, cycle count, uptime, and per-skill metrics.
- Emitted runtime snapshots on engine start, after actions, on a 500 ms idle cadence, and on engine stop.
- Updated `CycleExecutor` to count candidate node checks, not-ready skips, key-sent success, cast-start success, success, and failure.
- Added runtime snapshot handling in `useEngine`.
- Added `EngineRuntimeSnapshot` and expanded `SkillRuntimeState` frontend types.
- Added `applyRuntimeSnapshot` and sorted `skillRows` in the engine Pinia store.
- Connected `SkillStatusGrid` to the store and rendered it on the cycle editor page.
- Added Rust and frontend regression tests for runtime metrics.

## Files Changed

- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src/composables/useEngine.ts`
- `src/stores/engine.ts`
- `src/types/engine.ts`
- `src/components/engine/SkillStatusGrid.vue`
- `src/views/CycleEditorPage.vue`
- `src/__tests__/engine-store.test.ts`

## Root Cause / Key Decision

The engine already had `RuntimeState`, but command events did not serialize it. The smallest useful path was to keep `RuntimeState` inside the pure engine layer and add a command-layer DTO that converts it into a frontend-friendly event payload.

## Logs / Tests

- `cargo fmt`
- `cargo test` passed: 71 tests.
- `cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd exec vue-tsc --noEmit` passed.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- Metrics are still coarse. `key_sent_ok` and `cast_started` are counted on successful attempts because the current `SkillAttemptExecutor` does not expose intermediate stage events.
- Runtime snapshots are event-based only. `engine_status` still returns a minimal running flag.

## Next Step

Split skill attempt execution into observable stages or add an attempt event sink so runtime metrics can distinguish key send, cast start, completion, timeout, and retry paths precisely.
