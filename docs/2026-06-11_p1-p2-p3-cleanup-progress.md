# Progress

## Goal

按 P1、P2、P3 顺序处理审查中确认的高优先级问题。

## Done

- P1: `engine_stop` 改为等待引擎 task 协作退出，超时后 abort。
- P1: 引擎启动、预检和模拟路径复用完整 Profile 引用与表达式校验。
- P1: 将应用数据目录解析收敛到 `ProfileStore` 模块，并移除未声明的 `dirs` 依赖路径。
- P2: `backup_on_save` 保存前生成旧配置备份；移除未实现的 `auto_save` 配置字段。
- P2: 统一 `primary` monitor 的像素采样缓存 key，避免 ROI 与普通像素条件重复截屏。
- P2: 将前端 engine 事件监听句柄提升为模块级共享状态，避免多个 composable 实例各自残留监听。
- P3: 忽略本地 `.codegraph/` 索引目录，移除过期 `python-legacy` 忽略项。
- P3: 删除根目录重复 `assets/gw2/skills_all.json`，保留 `src-tauri/assets/gw2/skills_all.json` 作为唯一运行时数据源。

## Files Changed

- `.gitignore`
- `AGENTS.md`
- `src-tauri/src/lib.rs`
- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/commands/skill_cmd.rs`
- `src-tauri/src/capture/capturer.rs`
- `src-tauri/src/models/base.rs`
- `src/composables/useEngine.ts`
- `src/composables/useProfile.ts`
- `src/types/profile.ts`
- `src/views/SettingsPage.vue`
- `assets/gw2/skills_all.json`

## Root Cause / Key Decision

- 引擎生命周期不能只靠取消 token 和 UI 状态兜底，停止命令必须等待旧 task 结束。
- 启动路径必须与保存路径共享完整 Profile 校验，否则手工 TOML 或旧配置会在运行时静默失效。
- `auto_save` 没有安全的全局语义，保留字段会制造错误预期；`backup_on_save` 可以在持久化层可靠实现。
- GW2 技能数据只保留 Tauri 打包路径，避免仓库和包体双份资源。

## Logs / Tests

- `cargo test --manifest-path src-tauri\Cargo.toml`
- `cargo clippy --manifest-path src-tauri\Cargo.toml --all-targets -- -D warnings`
- `cargo fmt --manifest-path src-tauri\Cargo.toml --check`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`
- `git diff --check`

## Risks

- 工作区已有大量未提交修改，本次没有回滚或整理这些既有改动。
- `pnpm build` 仍有 Vite chunk size 警告，属于既有打包体积问题，不在本次 P1/P2/P3 范围内。

## Next Step

继续拆分 `CycleExecutor`、`CycleEditorPage.vue` 和 IPC 命令体量，降低后续状态机功能改动风险。
