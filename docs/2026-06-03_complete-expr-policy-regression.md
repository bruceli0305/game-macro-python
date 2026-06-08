# Progress

## Goal

Clean up the old synchronous attempt path enough to rely on pending attempts, then add direct regression coverage for complete expression policies.

## Done

- Removed the old synchronous `execute_skill` helper from the compiled code path.
- Removed the helper-only imports from `cycle_executor.rs`.
- Added a direct `RequireSignal` regression for `complete_expr`.
- Verified that `complete_expr=false` keeps the attempt pending until the complete timeout, then fails with `timeout`.
- Verified runtime metrics for that path: cast starts, success stays zero, and failure reason is recorded.

## Files Changed

- `src-tauri/src/engine/cycle_executor.rs`

## Root Cause / Key Decision

Pending attempts are now the execution path, but an old synchronous helper remained in the file. Because surrounding comments still contain damaged legacy encoding, the safest cleanup was to move the helper out of compilation without doing a broad text rewrite. The behavioral gap was direct coverage for `complete_expr` under `RequireSignal`, now covered with a timeout test.

## Logs / Tests

- `cargo fmt`
- `$env:CARGO_INCREMENTAL='0'; cargo test` passed: 75 tests.
- `$env:CARGO_INCREMENTAL='0'; cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd build` passed, including `vue-tsc --noEmit` and Vite build.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- `cycle_executor.rs` still contains commented legacy helper text and damaged comments. It is no longer compiled, but the file should get a focused encoding/comment cleanup pass.
- Complete expression success is covered indirectly by existing success paths; a direct `RequireSignal` success test would further tighten coverage.

## Next Step

Replace damaged comments in `cycle_executor.rs` with clean ASCII comments and remove the commented legacy helper block entirely.
