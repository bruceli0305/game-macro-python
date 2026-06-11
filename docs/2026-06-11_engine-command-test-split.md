# Progress

## Goal

Keep `src-tauri/src/commands/engine_cmd.rs` focused on IPC command wiring by moving its regression tests into a sibling test module.

## Done

- Moved the `engine_cmd.rs` `#[cfg(test)]` block to `src-tauri/src/commands/engine_cmd_tests.rs`.
- Left `engine_cmd.rs` with a small `#[path = "engine_cmd_tests.rs"] mod tests;` declaration.
- Reduced `engine_cmd.rs` from 669 lines to 264 lines.

## Files Changed

- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/commands/engine_cmd_tests.rs`

## Root Cause / Key Decision

The command file had already shed most production responsibilities into engine modules, but the inline test fixture still made it look and behave like a large mixed-ownership file. The tests exercise command-adjacent behavior and can stay under `commands/` while no longer dominating the production command implementation.

## Logs / Tests

- `cargo fmt`
- `cargo test` - 195 tests passed.
- `cargo clippy --all-targets -- -D warnings`

## Risks

- This is a structural test move only; it does not further split command orchestration helpers.
- The remaining production command layer is now small enough to audit, but future lifecycle changes should still keep task state transitions outside ad hoc command logic.

## Next Step

Re-audit the five cleanup items against current file sizes and verification evidence, then only continue if a concrete unhandled item remains.
