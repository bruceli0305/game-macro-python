# Progress

## Goal

Remove the stale capture plan/scanner path that suggested runtime pixel checks were executed through a planned batch scanner.

## Done

- Removed `capture::plan` and `capture::scanner`.
- Removed unused `CapturePlan` and `CaptureRegion` types from `capturer.rs`.
- Kept runtime sampling semantics explicit: engine execution uses `PixelSampler` implementations, primarily `CachedPixelSampler` in the engine loop and `DirectPixelSampler` in offline simulation.
- Updated older progress/audit docs so they no longer describe `CapturePlan` / `PixelScanner` as pending integration work.

## Files Changed

- `src-tauri/src/capture/mod.rs`
- `src-tauri/src/capture/capturer.rs`
- `src-tauri/src/capture/plan.rs`
- `src-tauri/src/capture/scanner.rs`
- `docs/2026-06-09_engine-performance-cache-progress.md`
- `docs/2026-06-09_project-health-audit.md`

## Root Cause / Key Decision

`CapturePlan` and `PixelScanner` were not called by production code. Keeping them made the capture layer look like it had a planned batch-sampling path, while actual engine execution used `CachedPixelSampler` directly through the `PixelSampler` trait. Deleting the stale path makes the capture boundary honest and avoids future performance assumptions based on dead abstractions.

## Logs / Tests

- `rg "CapturePlan|PixelScanner|capture::plan|capture::scanner|build_plan\(" src-tauri/src src docs`
  - No source references remain.
- `cargo fmt --manifest-path src-tauri\Cargo.toml`
- `cargo test --manifest-path src-tauri\Cargo.toml`
  - 195 passed
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`

## Risks

- This removes unused public Rust module exports. No in-repo caller used them, and the app has no external Rust API contract.
- It does not attempt a new batch capture implementation. Future performance work should extend `CachedPixelSampler` or add a real shared frame abstraction with direct engine integration.

## Next Step

Continue with the remaining frontend-heavy item: split `CycleEditorPage.vue` and reduce route chunk pressure.
