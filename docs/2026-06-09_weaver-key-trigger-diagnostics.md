# Progress

## Goal
检查 Weaver 循环运行时技能日志和状态，定位只有少量按键被触发的原因。

## Done
- 读取当前活跃 profile：`condition_weaver_pistol_dagger`。
- 采样当前屏幕中的 attunement、技能图标和施法条 ROI 点位。
- 确认发键少的主要原因是技能暗/亮判定阈值过低，不是缺少真实发键函数。
- 将内置循环预设中的 `pixel_skill_black` / `pixel_skill_not_black` tolerance 从 24 调整为 64。
- 同步修复本机当前活跃 profile 中的 91 个技能暗/亮表达式。

## Files Changed
- `src/assets/json/cycle-presets.json`
- `%LOCALAPPDATA%/game-macro-tauri/profiles/condition_weaver_pistol_dagger/profile.toml`

## Root Cause / Key Decision
当前屏幕采样中，多个已经暗掉的技能图标像素并不是纯黑，例如 `(34,5,2)`、`(47,25,8)`、`(50,20,8)`。原配置 `tolerance = 24` 会把这些暗图标误判为非黑，导致 `complete_expr = pixel_skill_black(...)` 长时间不满足。引擎随后只能等到 `complete_timeout_ms` 后按 `assume_success_after_timeout` 继续，所以表现为按键触发很少、节奏很慢。

将技能暗/亮判断阈值提高到 64 后，当前暗图标可被识别为 black；当前亮图标最大通道最低约 131，仍会被识别为 not black。F1-F4 attunement 颜色点仍保留原来的 24 阈值，避免状态识别过宽。

## Logs / Tests
- 当前屏幕采样：主 attunement 命中 Fire，副 attunement 命中 Earth。
- `node` JSON parse：通过。
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/role-profile-templates.test.ts src/__tests__/profile-validation.test.ts`：69 passed。
- `pnpm.cmd build`：通过，保留既有 chunk size warning。

## Risks
- 64 是基于当前截图和当前屏幕采样校准的经验值；如果 UI 亮度、后处理、分辨率或技能栏位置变化，仍需要重新取点。
- 当前运行中的桌面进程可能还加载着旧 profile，需要停止引擎后重新启动/重新加载 profile 才会使用新的本地 profile 配置。

## Next Step
增加运行态诊断视图：显示每个条件的最后一次采样 RGB、delta、black/not black 结果和失败原因，避免以后只能从日志侧猜测。
