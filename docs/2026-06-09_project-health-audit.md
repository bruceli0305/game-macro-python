# Progress

## Goal

梳理当前项目健康状态，重点检查明显 bug、巨型文件、中文乱码、重复资源和性能优化入口。

## Done

- 扫描当前工作树、文件体量、乱码文本和调试输出。
- 修复 Rust 源码中真实存在的乱码注释和一条 AST 编译错误文案。
- 移除前端正式源码中的 `console.log` 调试输出。
- 确认前端页面层没有直接调用 Tauri `invoke()`，IPC 仍集中在 composables。
- 确认 `assets/gw2/skills_all.json` 与 `src-tauri/assets/gw2/skills_all.json` 内容完全相同，各约 7.1 MB。

## Files Changed

- `src-tauri/src/engine/skill_attempt.rs`
- `src-tauri/src/ast/evaluator.rs`
- `src-tauri/src/ast/compiler.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src/composables/useHotkeys.ts`
- `src/views/SkillsPage.vue`
- `docs/2026-06-09_project-health-audit.md`

## Root Cause / Key Decision

- 乱码主要来自早期迁移时注释或文案被错误编码保存；配置文件本身通过 Node/Cargo 读取为正常中文，PowerShell 输出乱码不等同于文件损坏。
- `CycleExecutor` 已经超过 2600 行，且承担调度、条件求值、尝试推进、ROI 和测试，后续性能优化前应先明确拆分边界。
- 当前像素条件使用 `DirectPixelSampler`，每次采样都会重新枚举 monitor 并截屏；ROI provider 虽已有 tick cache，但真实采样仍会新建 `CaptureManager`。
- 重复 GW2 JSON 暂不直接删除，避免破坏 Tauri dev/build 的资源查找路径；后续应改为单一源文件加构建复制或明确 bundle 路径。

## Logs / Tests

- `cargo test --manifest-path src-tauri/Cargo.toml`
- `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`
- `git diff --check`

## Risks

- `expr_cache` 当前在 `CycleExecutor::new` 中构造，但运行时仍会在 tick 中重复编译 slot 条件表达式。
- `CapturePlan` / `PixelScanner` 已存在，但没有真正接入引擎执行路径，多个像素条件会重复截图。
- `ahk/` 仍是未跟踪参考目录，需要决定是加入版本控制、移入 docs/reference，还是写入 `.gitignore`。
- `skills_all.json` 重复占用仓库和打包体积，需要单独处理资源归属。

## Next Step

1. 先提交本轮健康清理与上一轮 ROI 统计改动。
2. 拆出 slot 级预编译运行时配置，避免 tick 内重复 `compile_expr_json`。
3. 引入 tick 级 `FrameSampler`，让 Pixel 条件与 ROI 条件共享同一轮截图缓存。
4. 单独处理 GW2 JSON 资源去重和 `ahk/` 目录归属。
