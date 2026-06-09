# Progress

## Goal

删除已经不再承担运行职责的 `python-legacy` 旧实现，并将当前 Tauri/Vue/Rust 代码作为主线状态推送到 `main`。

## Done

- 检查 `python-legacy` 内容：旧 PySide/Python UI、旧 runtime、旧 tests、旧 GW2 JSON 资源。
- 确认当前新栈不再运行 Python 入口。
- 移除 Rust GW2 skill search 中对 `../python-legacy/assets/json/gw2/skills_all.json` 的 fallback。
- 确认根目录 `assets/gw2/skills_all.json` 与旧目录同名文件 hash 一致，可继续作为技能搜索数据源。
- 删除 `python-legacy` 目录。
- 清理 Rust 注释中指向 `python-legacy` 的过期说明。

## Files Changed

- `python-legacy/`
- `src-tauri/src/commands/skill_cmd.rs`
- `src-tauri/src/ast/nodes.rs`
- `src-tauri/src/capture/capturer.rs`
- `src-tauri/src/engine/runtime_state.rs`
- `src-tauri/src/engine/scheduler.rs`
- `src-tauri/src/engine/skill_attempt.rs`
- `src-tauri/src/input/key_sender.rs`
- `src-tauri/src/models/*.rs`

## Root Cause / Key Decision

项目已迁移到 Tauri 2 + Vue 3 + Rust，`python-legacy` 不再是开发或运行主线。继续保留旧目录会制造搜索噪音、重复模型、重复 runtime 逻辑和过期依赖判断。

唯一有效依赖是旧目录里的 GW2 技能 JSON fallback，但根目录已有同 hash 的 `assets/gw2/skills_all.json`，因此可以去掉旧目录依赖后删除。

## Logs / Tests

- `rg "python-legacy"`: no matches
- `pnpm.cmd exec vue-tsc --noEmit`: passed
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/role-profile-templates.test.ts src/__tests__/profile-validation.test.ts`: passed, 16 files / 68 tests
- `cargo test`: passed, 175 tests
- `cargo clippy --no-default-features -- -D warnings`: passed
- `pnpm.cmd build`: passed, with existing Vite chunk-size warning
- `git diff --check`: passed, with CRLF warnings only

## Risks

- `professions_all.json` and `specializations_all.json` were only present under `python-legacy`; current code does not reference them. If future GW2 data import needs them, add them explicitly under the active `assets/` structure.

## Next Step

Push this stable state to `main`, then create a new loop-debug branch for cycle tuning work.
