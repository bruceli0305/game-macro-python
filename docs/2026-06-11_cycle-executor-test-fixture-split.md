# Progress

## Goal

Move the large `CycleExecutor` test fixture out of the implementation file so backend state-machine code can be refactored without carrying thousands of test lines in the same source file.

## Done

- Moved the inline `#[cfg(test)] mod tests` content from `cycle_executor.rs` into `cycle_executor_tests.rs`.
- Kept the test module as a child of `cycle_executor` via `#[path = "cycle_executor_tests.rs"] mod tests;`, so existing private helper coverage remains intact.
- Reduced `cycle_executor.rs` from 2617 lines to 382 lines.
- Preserved existing test names and coverage paths under `engine::cycle_executor::tests::*`.

## Files Changed

- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/engine/cycle_executor_tests.rs`

## Root Cause / Key Decision

The executor implementation was no longer thousands of lines of production code, but the embedded test fixture still made the file appear and behave like a large mixed-responsibility module. Moving tests to a sibling file keeps behavior coverage close while making the production implementation easier to scan and split further.

## Logs / Tests

- `cargo fmt --manifest-path src-tauri\Cargo.toml`
- `cargo test --manifest-path src-tauri\Cargo.toml`
  - 195 passed
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`

## Risks

- This is a structural test move only. It does not split the `tick` phase-scan loop yet.
- The test-support helpers are still large and can be broken down further if they start blocking focused test maintenance.

## Next Step

Split the main phase scan loop out of `CycleExecutor::tick`, then continue with capture plan/scanner cleanup or `CycleEditorPage.vue` decomposition.
