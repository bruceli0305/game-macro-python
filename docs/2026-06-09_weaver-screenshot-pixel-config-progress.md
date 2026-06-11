# Progress

## Goal

根据 `img/` 中 1920x1080 游戏截图，为 Condition Weaver 内置角色补齐可直接落地的取色配置。

## Done

- 从 `gw005.jpg` 到 `gw021.jpg` 对比技能栏状态。
- 将 Weaver 普通技能、双元素技能、Dagger 4/5、工具技能、精英技能改为截图中的实际槽位坐标和颜色。
- 将 F1-F4 职业技能键位按截图改为：
  - Fire: `Q`
  - Water: `E`
  - Air: `R`
  - Earth: `T`
- 由于 F1-F4 图标尺寸和普通技能槽不同，且图标中心不能表达当前 Weaver 双元素状态，元素判断点改为采样职业技能下方状态条：
  - Primary element: `x=650, y=972`
  - Secondary element: `x=800, y=972`
- 为 Condition Weaver profile seed 增加默认施法条 ROI：
  - `x=850`
  - `y=815`
  - `width=219`
  - `height=19`
  - `border_color=0xBCBCBC`

## Files Changed

- `src/assets/json/role-profile-seeds.json`
- `src/utils/role-profile-templates.ts`
- `src/__tests__/role-profile-templates.test.ts`

## Root Cause / Key Decision

F1-F4 图标中心只表示按钮图案，不表示当前主/副元素状态。截图中 Weaver 的主/副元素状态在 F1-F4 下方状态条中更稳定：

- 左段状态条颜色表示当前主元素。
- 右侧尾段颜色表示当前副元素。

因此 `attune_*_primary` 和 `attune_*_secondary` 使用共享坐标、不同颜色，而不是每个元素使用各自图标中心坐标。

## Logs / Tests

- `node` JSON parse: passed
- `pnpm.cmd exec vue-tsc --noEmit`: passed
- `pnpm.cmd test -- src/__tests__/role-profile-templates.test.ts src/__tests__/cycle-presets.test.ts src/__tests__/profile-validation.test.ts`: passed, 16 files / 69 tests

## Risks

- 当前坐标基于 1920x1080 和这套 UI 缩放/键位。分辨率、UI 缩放、技能栏位置或键位变化后需要重新取色。
- `Fire/Air Dual 3` 未在截图序列中直接出现，暂用同槽位的可见亮区配置，后续实战帧应补采。
- 施法条 ROI 基于当前角色位置和镜头角度，进入实战场景后应在设置页测试 ROI 命中率。

## Next Step

启动桌面程序，切换到 Condition Weaver profile，先验证元素状态 observer 是否能随 Q/E/R/T 切换实时更新，再验证施法条 ROI 的 changed/border 状态。
