# Progress

## Goal

Introduce an in-progress attempt state so skill attempts can advance across engine ticks without blocking the async engine task.

## Done

- Added a private `PendingAttempt` state to `CycleExecutor`.
- Added pending stages for start wait, retry delay, and complete wait.
- Changed `CycleExecutor::tick` to advance an active pending attempt before selecting new phase candidates.
- Moved attempt start into `begin_skill_attempt`, which emits attempt/key-sent runtime events and stores pending state.
- Added non-blocking complete wait behavior for `AssumeSuccess`: nonzero `readbar_ms` now finishes on a later tick instead of completing immediately.
- Added a regression test that verifies a 100 ms readbar stays in progress at 50 ms and completes at 100 ms.

## Files Changed

- `src-tauri/src/engine/cycle_executor.rs`

## Root Cause / Key Decision

The engine had already stopped sleeping inside the outer loop, but skill attempts still behaved like a synchronous function. The next step is to make attempts resumable. This change starts with the safest path: complete-wait timing for `AssumeSuccess`, while preserving existing immediate behavior for zero-readbar skills.

## Logs / Tests

- `cargo fmt`
- `$env:CARGO_INCREMENTAL='0'; cargo clippy --all-targets -- -D warnings` passed.
- `$env:CARGO_INCREMENTAL='0'; cargo test` passed: 73 tests.
- `pnpm.cmd build` passed, including `vue-tsc --noEmit` and Vite build.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- Start signal configuration is still not represented in the Rust `SkillSlot` model, so pending start wait currently uses the default true start expression.
- The old synchronous `execute_skill` helper remains as dead code because the file still contains damaged legacy comment encoding that made surgical deletion unreliable. It is not called by `tick`.
- Complete signal expressions are structurally supported in pending state but are not yet wired from profile data.

## Next Step

Add explicit start/complete expression fields to the cycle skill slot model and wire them into `PendingAttempt`, then remove the old synchronous helper during a dedicated encoding cleanup of `cycle_executor.rs`.
