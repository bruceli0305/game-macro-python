# Progress

## Goal

Make engine runtime metrics reflect skill attempt stages directly instead of inferring key-send and cast-start metrics from the final attempt outcome.

## Done

- Added `AttemptEvent` events to `SkillAttemptExecutor`.
- Kept the existing `exec_skill_node` API and added `exec_skill_node_with_events` for observable execution.
- Emitted attempt started, key sent, cast started, complete wait, success, failure, and stopped events from the skill attempt state machine.
- Changed `CycleExecutor` to collect attempt events and apply them to `RuntimeState`.
- Updated runtime stage transitions for `StartWait`, `CompleteWait`, and `Stopped`.
- Added a regression test for retry exhaustion where keys are sent but cast start never occurs.

## Files Changed

- `src-tauri/src/engine/skill_attempt.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/engine/runtime_state.rs`

## Root Cause / Key Decision

Runtime metrics were being inferred in `CycleExecutor` after `SkillAttemptExecutor` returned a final `Outcome`. That made successful attempts mark `key_sent_ok` and `cast_started` together, but it could not represent partial paths such as repeated key sends followed by `no_cast_start`. The state machine is the source of truth for these transitions, so it now emits structured attempt events and the executor applies them after the immutable runtime borrow ends.

## Logs / Tests

- `cargo fmt`
- `cargo test` initially hit a Windows incremental cache access-denied error.
- `$env:CARGO_INCREMENTAL='0'; cargo test` passed: 72 tests.
- `$env:CARGO_INCREMENTAL='0'; cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd build` passed, including `vue-tsc --noEmit` and Vite build.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- Runtime metrics are still applied after each synchronous attempt returns, so the frontend receives precise aggregate/stage results at snapshot time, not streaming sub-stage events during an attempt.
- `SkillAttemptExecutor` still uses single-sample polling placeholders; true timed polling remains separate engine work.

## Next Step

Replace the placeholder single-sample `poll_expr_until` behavior with a caller-driven or async polling model so start and complete waits can respect timeout and poll intervals.
