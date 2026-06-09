# Progress

## Goal

将 Condition Weaver Pistol/Dagger 从通用武器槽位配置推进到可落地的帧驱动模板。

## Done

- 将 `weaver_weapon_2/3/4/5` 拆成语义技能，例如 Fire Pistol 2、Earth Pistol 2、Fire/Earth Dual 3、Ring of Fire、Churning Earth。
- 将 `weaver_utility_8/9` 和 `weaver_elite_0` 拆成明确技能：Signet of Fire、Signet of Earth、Primordial Stance、Weave Self。
- 为 Weaver 增加主/副元素点位：
  - `attune_fire_primary`
  - `attune_water_primary`
  - `attune_air_primary`
  - `attune_earth_primary`
  - `attune_fire_secondary`
  - `attune_water_secondary`
  - `attune_air_secondary`
  - `attune_earth_secondary`
- 为循环 preset 增加 `weaver_attunement_watchers` observer lane，用当前帧点位刷新 `attunement` 标记。
- 将 Weave Self burst 和 Fire/Earth loop 的技能槽改为“元素点位匹配 + 技能 ready 像素”共同触发。
- 增加 `weaver_dagger_priority` lane，将 Dagger 4/5 按当前元素组合拆开判断。

## Files Changed

- `src/assets/json/role-profile-seeds.json`
- `src/assets/json/cycle-presets.json`
- `src/__tests__/cycle-presets.test.ts`
- `src/__tests__/role-profile-templates.test.ts`

## Root Cause / Key Decision

旧模板只知道当前要按武器 2/3/4/5，但 Weaver 的同一个按键会随主/副元素变化成不同技能。

因此不能只做顺序执行或槽位级配置。现在的资产层先把技能语义拆开，再用当前帧的主/副元素点位作为条件，让编辑器里能表达“当前是 Fire/Earth 时才释放 Fire/Earth Dual 3”这类规则。

## Logs / Tests

- `node` JSON parse: passed
- `pnpm.cmd exec vue-tsc --noEmit`: passed
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/role-profile-templates.test.ts src/__tests__/profile-validation.test.ts`: passed, 16 files / 68 tests

## Risks

- 点位坐标和颜色仍是模板 seed，必须在用户 UI 缩放、皮肤和技能栏布局下重新取色。
- `Primordial Stance` 默认放在 key `7`，需要按真实技能栏调整。
- 当前仍是数据资产层改造，后续还需要编辑器 UI 更清晰地展示“元素状态条件 -> 技能语义槽 -> 释放确认”。

## Next Step

在循环编辑器中补强 Weaver 这类 frame-driven profile 的配置体验：按角色切换后展示语义技能、元素条件和点位校准入口，减少用户直接编辑 AST 的成本。
