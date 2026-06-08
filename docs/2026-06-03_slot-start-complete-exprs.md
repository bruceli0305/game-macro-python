# Progress

## Goal

Add explicit start and complete signal expressions to cycle skill slots and wire them into pending attempt execution.

## Done

- Added `start_expr` and `complete_expr` to Rust `SkillSlot`.
- Added `#[serde(default)]` on optional expression fields so existing TOML profiles can still deserialize.
- Synced frontend `SkillSlot` TypeScript fields.
- Updated cycle editor slot defaults to include the new expression fields.
- Added start and complete expression builders to `SkillEditModal`.
- Wired `CycleExecutor` pending attempts to compile `slot.start_expr` and `slot.complete_expr`.
- Added a regression test proving `start_expr=false` waits until start timeout and fails without marking cast start.
- Added a test helper for cycle executor slot fixtures so model field changes are less noisy.

## Files Changed

- `src-tauri/src/models/cycle.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src/types/cycle.ts`
- `src/views/CycleEditorPage.vue`
- `src/components/editor/SkillEditModal.vue`

## Root Cause / Key Decision

Pending attempt state existed, but start and complete signal expressions were not part of the slot model. This meant the engine could only use a default true start expression and no complete expression. The model now carries these signals explicitly, with backward-compatible deserialization for older profiles.

## Logs / Tests

- `cargo fmt`
- `$env:CARGO_INCREMENTAL='0'; cargo test` passed: 74 tests.
- `$env:CARGO_INCREMENTAL='0'; cargo clippy --all-targets -- -D warnings` passed.
- `pnpm.cmd build` passed, including `vue-tsc --noEmit` and Vite build.
- `pnpm.cmd exec vitest run` passed: 2 files, 3 tests.

## Risks

- `SkillEditModal.vue` and `cycle_executor.rs` still contain damaged legacy text encoding, so UI labels are not fully cleaned up.
- The old synchronous `execute_skill` helper remains as dead code because deleting it cleanly is blocked by the same damaged text region.
- Complete expression behavior is wired but only indirectly covered; a dedicated complete signal test should be added next.

## Next Step

Clean the damaged encoding in `cycle_executor.rs` enough to remove the dead synchronous helper, then add direct regression coverage for `complete_expr` policies.
