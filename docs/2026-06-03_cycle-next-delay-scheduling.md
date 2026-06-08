# Progress

## Goal

Connect skill attempt `next_delay_ms` results to the cycle scheduler so the engine does not immediately re-fire a skill on the next short tick.

## Done

- Added `next_ready_ms` to `CycleExecState`.
- Added a tick gate in `CycleExecutor::tick` that returns early until the executor is due.
- Changed `execute_skill` to return the full `ExecutionResult` instead of only an outcome string.
- Set `next_ready_ms` from `now_ms + ExecutionResult.next_delay_ms` after each attempted skill.
- Updated cycle executor tests to assert that the default 50 ms post-attempt gap blocks immediate re-fire and allows execution after the due time.

## Files Changed

- `src-tauri/src/engine/cycle_executor.rs`

## Root Cause / Key Decision

`SkillAttemptExecutor` already returned `next_delay_ms`, but `CycleExecutor` ignored it. That made simulations and live ticks capable of firing again on the next scheduler tick, even when the attempt result requested a gap. The fix keeps scheduling non-blocking by storing the next due timestamp instead of sleeping inside the engine state machine.

## Logs / Tests

- `cargo fmt`
- `$env:CARGO_INCREMENTAL='0'; cargo test` passed: 72 tests.
- `$env:CARGO_INCREMENTAL='0'; cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd build` passed, including `vue-tsc --noEmit` and Vite build.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- This only applies a single global executor delay. Per-skill cooldown due times and in-progress attempt polling are still future work.
- `poll_expr_until` still samples once per attempt; start and complete signal waits need a non-blocking attempt state model before they can fully honor timeout and poll intervals.

## Next Step

Introduce an in-progress attempt state so start/complete polling can advance across ticks without blocking the async engine task.
