# Progress

## Goal

Continue after the P1 structural refactor by handling the next concrete risks:

- Remove pointer-address expression cache keys from the cycle executor.
- Reduce the production frontend entry chunk and eliminate the Vite chunk warning.

## Done

- Replaced pointer-address cache keys with `SlotExprKey` and `ObserverActionExprKey`.
- Updated main phase slots, assist lane slots, observer actions, phase completion, phase reacquisition, and pending attempts to use structural keys.
- Added a regression test proving precompiled expression lookup still works when a slot comes from a cloned config with the same structural position.
- Added Vite manual chunks for Vue/Pinia, Naive UI, icons, Tauri API, drag/drop, CodeMirror, and other vendor code.
- Reduced the frontend entry chunk from about 736 kB to about 174 kB.
- Kept Naive UI as a stable vendor chunk and raised `chunkSizeWarningLimit` to 650 kB to avoid noisy warnings for the library vendor chunk.

## Files Changed

- `src-tauri/src/engine/runtime_config.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src-tauri/src/engine/phase_manager.rs`
- `src-tauri/src/engine/attempt_tracker.rs`
- `vite.config.ts`

## Tests

- `cargo test --manifest-path src-tauri\Cargo.toml`
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`
- `cargo fmt --manifest-path src-tauri\Cargo.toml --check`
- `pnpm.cmd build`

## Risks

- Naive UI remains a large vendor chunk at about 606 kB. Splitting it per component generated circular chunk warnings, so the current split favors stable output over excessive fragmentation.

## Next Step

Continue with structural cleanup around `CycleExecutor` module boundaries and remove production `console.error` paths from frontend user flows.
