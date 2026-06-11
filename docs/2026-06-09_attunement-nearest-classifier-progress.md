# Progress

## Goal
修正 Weaver 形态判断：形态条是动态颜色/动画，不能继续依赖单点 `pixel_point + tolerance` 做 Fire/Water/Air/Earth 判断。

## Done
- 新增 AST 条件 `pixel_point_nearest`。
- `pixel_point_nearest` 使用同一采样点在多个候选点目标色之间做最近颜色分类：
  - `expected_point_id`：期望分类。
  - `candidate_point_ids`：候选颜色点。
  - `max_delta`：最近颜色允许的最大差值。
  - `min_margin`：最近颜色与第二近颜色之间的最小差距。
- 后端编译器、探针收集、求值器均支持该条件。
- 前端类型、配置校验、条件编辑器均支持该条件。
- 将 Weaver 内置循环预设中的 174 个 attunement `pixel_point` 判断替换为 `pixel_point_nearest`。
- 同步修改当前本机活跃 profile：
  - `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`

## Files Changed
- `src-tauri/src/ast/nodes.rs`
- `src-tauri/src/ast/compiler.rs`
- `src-tauri/src/ast/evaluator.rs`
- `src/types/ast.ts`
- `src/utils/profile-validation.ts`
- `src/components/editor/ConditionBuilder.vue`
- `src/assets/json/cycle-presets.json`
- `src/__tests__/cycle-presets.test.ts`
- `src/__tests__/profile-validation.test.ts`
- `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`

## Root Cause / Key Decision
扩大普通容差会导致多个形态同时匹配。例如当前副形态点更接近 Earth，但如果容差过大也可能被 Fire 命中。`pixel_point_nearest` 改为分类问题：只选择最近颜色，并要求它和第二近候选拉开 `min_margin`，可以避免“多形态同时为 true”。

当前 Weaver 预设参数：
- `max_delta = 96`
- `min_margin = 20`

## Logs / Tests
- `cargo test`：179 passed。
- `cargo clippy --no-default-features -- -D warnings`：通过。
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/role-profile-templates.test.ts src/__tests__/profile-validation.test.ts`：70 passed。
- `pnpm.cmd build`：通过，保留既有 chunk size warning。
- `cycle-presets.json` / `role-profile-seeds.json` JSON parse：通过。
- 当前活跃 profile TOML parse：通过。

## Risks
- 当前仍采样形态条上的语义点，只是由“容差匹配”改为“最近分类”。如果动画过渡帧导致最近颜色与第二近颜色距离小于 `min_margin`，条件会短暂 false，这是预期的保守行为。
- 后续更稳的方案是把形态采样点迁到更稳定的 F1-F4 图标或固定 UI 元素，并在运行态诊断中展示最近分类的 best/second/margin。

## Next Step
增加运行态条件诊断：展示当前 RGB、最近候选、第二候选、delta 和 margin，便于现场调参。
