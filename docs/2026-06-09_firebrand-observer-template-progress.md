# Progress

## Goal

把“条件命中后只刷新计时器、不发键”的后台 watcher 流程落到通用 observer lane 配置中。`ahk/急速燃.ahk` 仅作为需求样例，不作为专用兼容目标。

## Done

- 在急速燃角色循环配置中新增 `firebrand_cast_watchers` observer lane。
- 将四个后台 watcher 映射为 observer action：
  - `ty2 != black && lastKeyTime2 >= 1000` -> `ty2_seen`
  - `ty3 != black && lastKeyTime3 >= 1000` -> `ty3_seen`
  - `point3 == color && lastKeyTime4 >= 1000` -> `point3_seen`
  - `point4 == color && lastKeyTime5 >= 1000` -> `point4_seen`
- 保持原 Assist Lane 继续负责真实技能补放，observer lane 只更新 runtime state。
- 循环编辑器移除“选择模板 / 应用模板”入口，改为只编辑 active profile 当前角色配置。
- Profile 切换事件改为目标配置加载完成后再广播，避免页面在切换中途读取旧数据。

## Files Changed

- `src/utils/cycle-presets.ts`
- `src/__tests__/cycle-presets.test.ts`
- `src/views/CycleEditorPage.vue`
- `src/components/AppLayout.vue`
- `src/composables/useProfile.ts`

## Root Cause / Key Decision

旧脚本里的 `SendLoop(key, 0)` 不代表释放技能，而是借用旧函数形态执行“检测后刷新计时器”。迁移后不能建假技能槽，也不能放进 Assist Lane 发键路径，应使用通用 observer action slot。

## Logs / Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/profile-validation.test.ts`
- Browser DOM check: `/cycle-editor` no longer shows manual template select/apply controls.

## Risks

- `fb_point3_watch` / `fb_point4_watch` 仍需要在点位页面按实际 UI 标定。
- `fb_ty2_assist` / `fb_ty3_assist` 需要对应技能像素配置后，observer 条件才会真实生效。

## Next Step

继续把点位、技能 ID、按键和循环编排沉淀到对应角色 Profile 中。循环编辑器只随 active profile 切换加载当前角色配置，不再作为手动模板加载入口。
