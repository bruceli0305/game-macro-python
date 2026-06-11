# Progress

## Goal

Continue reducing `CycleExecutor` and nearby engine modules by moving shared readiness and runtime-action logic behind focused internal modules.

## Done

- Added `engine::readiness` for skill readiness checks, expression evaluation, cooldown helpers, ammo pixel checks, and per-cycle shot limits.
- Added `engine::runtime_actions` for runtime action application, runtime-action logging, phase-entry counter reset, and counter reset-to-initial behavior.
- Removed the migrated readiness block from `cycle_executor.rs`.
- Removed the migrated runtime-action block from `phase_manager.rs`.
- Kept the existing public command surface, event names, log event fields, and scheduler behavior unchanged.

## Files Changed

- `src-tauri/src/engine/readiness.rs`
- `src-tauri/src/engine/runtime_actions.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/engine/phase_manager.rs`
- `src-tauri/src/engine/mod.rs`

## Root Cause / Key Decision

`CycleExecutor` still carried shared readiness helpers that were used by the main loop, phase completion, lane execution, and pending attempts. `phase_manager.rs` also mixed phase transition rules with runtime action application. Both groups have clear responsibilities and existing behavior coverage, so they can be moved without changing state-machine semantics.

## Logs / Tests

- `cargo fmt --manifest-path src-tauri\Cargo.toml`
- `cargo test --manifest-path src-tauri\Cargo.toml`
  - 195 passed
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`

## Risks

- The large `cycle_executor.rs` test fixture remains in place, so the file is still large even after production logic was moved.
- `CycleExecutor::tick` still contains the main phase scan loop. That should be the next backend split after test fixtures are isolated.

## Next Step

Move `cycle_executor.rs` test fixtures into a dedicated test-support module, then split the main phase scan loop from `tick`.
