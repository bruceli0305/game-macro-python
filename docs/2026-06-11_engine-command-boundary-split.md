# Progress

## Goal

Thin the engine IPC command layer while keeping engine start, preflight, simulation, and runtime event behavior unchanged.

## Done

- Moved active profile loading, engine validation, preflight report building, and attempt config mapping into `engine::profile_config`.
- Moved offline simulation, pixel override sampling, profile-content simulation, and IPC smoke fixture generation into `engine::simulation`.
- Moved runtime snapshot payload mapping into `engine::runtime_payload`.
- Reduced `commands/engine_cmd.rs` production responsibilities to Tauri command glue, task lifecycle orchestration, and event emission.

## Files Changed

- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/engine/profile_config.rs`
- `src-tauri/src/engine/simulation.rs`
- `src-tauri/src/engine/runtime_payload.rs`
- `src-tauri/src/engine/mod.rs`

## Root Cause / Key Decision

`engine_cmd.rs` mixed IPC entrypoints with profile semantics, simulation execution, runtime payload mapping, and smoke fixture construction. The command module now delegates those non-Tauri responsibilities to engine modules, which keeps command behavior stable while making the boundary easier to audit.

## Logs / Tests

- `cargo fmt --manifest-path src-tauri\Cargo.toml`
- `cargo test --manifest-path src-tauri\Cargo.toml`
  - 195 passed
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`

## Risks

- Existing tests remain in `commands/engine_cmd.rs` for now, even though their target logic has moved. They still verify the migrated APIs, but a later cleanup should move those fixtures into the new modules.
- The engine loop itself still lives in `engine_cmd.rs` because it emits Tauri events directly. A deeper split would need an explicit event sink abstraction.

## Next Step

Continue the five-item cleanup by extracting `CycleExecutor` readiness/runtime-action logic and moving its large test fixture surface out of the implementation file.
