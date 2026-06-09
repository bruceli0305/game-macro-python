# Progress

## Goal

完成两个开发切片：

1. 修复当前主要页面的用户可见中文乱码。
2. 增加施法条 ROI 视觉检测配置与即时检测能力。

## Done

- 修复循环编辑器顶部统计、运行控制标题、Phase 注释等乱码。
- 设置页已正常展示基础配置、读条与完成检测、执行设置等中文文案。
- `base.cast_bar` 新增 `roi` 配置，包含矩形区域、基准色、变化阈值、边框色阈值和确认帧数。
- 新增 Tauri 命令 `capture_cast_bar_roi`：
  - 截取指定显示器上的 ROI 矩形。
  - 计算平均色。
  - 计算与基准色的变化比例。
  - 计算边框色命中比例。
  - 返回 `changed_from_baseline` 与 `border_visible` 两个布尔信号。
- 设置页新增 ROI 校准入口：
  - 鼠标设为左上角。
  - 鼠标设为右下角。
  - 采样基准。
  - 测试 ROI。
- 前后端保存校验已支持 `cast_bar.mode = "roi"`，ROI 模式不再要求 `point_id`。
- 新增 ROI AST 条件：
  - `cast_bar_roi_changed`
  - `cast_bar_roi_border_visible`
  - `cast_bar_roi_gone`
- `CycleExecutor` 已可把 `base.cast_bar.roi` 转成运行时 ROI Provider，供 `start_expr` / `complete_expr` 求值。
- 技能编辑弹窗已新增 ROI 模板：
  - 释放开始：施法条 ROI 变化、Castbar Clarity 边框出现。
  - 释放完成：施法条 ROI 消失。
- 通用 `ConditionBuilder` 已支持直接选择三种 ROI 条件。

## Files Changed

- `src-tauri/src/models/base.rs`
- `src-tauri/src/store/profile_store.rs`
- `src-tauri/src/commands/capture_cmd.rs`
- `src-tauri/src/commands/profile_cmd.rs`
- `src-tauri/src/lib.rs`
- `src-tauri/src/capture/cast_bar_roi.rs`
- `src-tauri/src/capture/mod.rs`
- `src-tauri/src/ast/nodes.rs`
- `src-tauri/src/ast/compiler.rs`
- `src-tauri/src/ast/evaluator.rs`
- `src-tauri/src/commands/engine_cmd.rs`
- `src-tauri/src/engine/skill_attempt.rs`
- `src-tauri/src/engine/cycle_executor.rs`
- `src/types/profile.ts`
- `src/types/ast.ts`
- `src/composables/useProfile.ts`
- `src/composables/useCapture.ts`
- `src/utils/detection-templates.ts`
- `src/utils/profile-validation.ts`
- `src/views/SettingsPage.vue`
- `src/views/CycleEditorPage.vue`
- `src/components/editor/ConditionBuilder.vue`
- `src/components/editor/SkillEditModal.vue`
- `src/__tests__/profile-validation.test.ts`
- `src/__tests__/detection-templates.test.ts`

## Root Cause / Key Decision

`Castbar Clarity` 的内部 hook 能力不适合迁入本项目；本项目继续遵守“不读内存、不注入进程”的边界。

ROI 方案选择屏幕截图检测：利用 Castbar Clarity 强化后的可见施法条边框和区域变化，但只观察屏幕像素，不依赖游戏内部对象。

ROI 条件选择放进 AST，而不是写死在技能槽逻辑里。这样开始检测、完成检测、普通条件和后续复杂组合都能复用同一套表达式。

## Logs / Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`：61 passed
- `pnpm.cmd build`
- `cargo check --all-targets`
- `cargo fmt --all -- --check`
- `cargo test`：165 passed
- `cargo clippy --all-targets -- -D warnings`
- `git diff --check`：通过，仅有 CRLF 提示
- Browser smoke：
  - `/settings` 显示“启用施法条 ROI 检测”“鼠标设为左上角”“测试 ROI”等配置项。
  - `/cycle-editor` 显示“技能槽”“运行控制”，关键区域无已知乱码。
  - 构建产物包含“施法条 ROI 变化”“Castbar Clarity 边框出现”“施法条 ROI 消失”三个模板文案。

## Risks

- ROI 坐标需要用户手动校准，后续应提供拖框式选择体验。
- 不同分辨率、UI 缩放、Castbar Clarity 边框设置会影响阈值，需要继续做实机采样。
- ROI Provider 当前每次求值会即时截屏；后续如果多个条件同 tick 组合，应考虑按 tick 缓存 ROI 采样结果，避免重复截图。

## Next Step

1. 做 ROI 检测延迟统计，比较 30ms、50ms、80ms 轮询下的稳定性和 CPU 占用。
2. 为 ROI Provider 增加 tick 级采样缓存，避免同一轮多条件重复截图。
3. 增加拖框式 ROI 选择体验，降低手工填坐标成本。
