# Progress

## Goal

降低引擎 tick 热路径开销，优先处理条件表达式重复编译和同 tick 多个像素条件重复截图。

## Done

- 将 `CycleExecutor` 的 slot 条件、start 条件、complete 条件改为构造时预编译。
- 将 phase transition rule 条件改为构造时预编译，并按 phase/rule 下标读取，避免运行时重复编译。
- 新增 `PixelSampler::begin_tick()` 默认方法，执行器每轮 tick 会通知 sampler。
- 新增 `CachedPixelSampler`，真实引擎循环同一 tick 内同一 monitor 只截取一帧，后续像素条件复用该帧。
- 真实引擎运行路径接入 `CachedPixelSampler`；离线模拟和 pixel override 仍保留原采样路径。
- 增加回归测试，覆盖预编译缓存包含 phase slot、assist slot、transition rule，以及同一 skill 多 slot 条件不被合并。

## Files Changed

- `src-tauri/src/ast/evaluator.rs`
- `src-tauri/src/capture/capturer.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/engine/cycle_executor.rs`

## Root Cause / Key Decision

- 之前 `CycleExecutor::new()` 虽然构造了 `expr_cache`，但运行时仍在 `check_skill_ready()`、`begin_skill_attempt()` 和 phase transition 判断中调用 `compile_expr_json()`。
- 旧缓存按 `skill_id` 组织，不适合同一技能出现在多个 slot 且条件不同的情况；本次改为 slot 指针 key，transition rule 使用 phase/rule 下标。
- `xcap::Monitor` 在 Windows 上不是 `Send + Sync`，不能长期保存在 `PixelSampler` 内，否则 Tauri async task 无法 `spawn`。因此 `CachedPixelSampler` 只缓存 `RgbaImage` 和 monitor 偏移，monitor 枚举对象只在同步采样调用内短暂存在。

## Logs / Tests

- `cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check`
- `cargo test --manifest-path src-tauri/Cargo.toml`：169 passed
- `cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`：61 passed
- `pnpm.cmd build`
- `git diff --check`：仅 LF/CRLF 提示

## Risks

- `CachedPixelSampler` 对空 monitor 名称仍需先枚举 monitor 来解析 frame key；常规配置应使用已保存的 monitor 名称或 `primary`。
- ROI 采样目前仍走独立 provider 和截图路径，尚未与 pixel sampler 共享同一帧。
- Legacy `CapturePlan` / `PixelScanner` modules were removed on 2026-06-11; runtime sampling is explicitly through `PixelSampler` implementations.

## Next Step

1. 运行一次桌面程序手动观察真实引擎启动、运行和停止。
2. 将 ROI provider 改造为可复用 tick frame，减少 ROI 与 pixel 条件之间的截图重复。
3. 拆分 `cycle_executor.rs`，把预编译 runtime config、attempt 推进、phase transition 分离到独立模块。
