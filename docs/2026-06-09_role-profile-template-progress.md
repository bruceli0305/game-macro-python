# Progress

## Goal

把循环样例沉淀成通用角色 Profile 初始化数据，而不是在循环编辑器里手动套模板。

## Done

- 新增内置角色 Profile 模板层，Profile 内直接包含：
  - `skills`
  - `points`
  - `rotations`
  - `state_schema`
- 侧边栏角色下拉合并显示已保存 Profile 和内置角色 Profile。
- 首次选择内置角色时自动创建并保存对应 Profile，然后切换 active profile。
- 修复角色下拉 `v-model` 竞态：改为单向 `:value`，由 `switchProfile` 完成状态切换。
- 保存校验覆盖内置角色 Profile，确保 rotation 引用到的 skill/point 在同一 Profile 内存在。

## Files Changed

- `src/utils/role-profile-templates.ts`
- `src/__tests__/role-profile-templates.test.ts`
- `src/components/AppLayout.vue`

## Root Cause / Key Decision

循环编辑器不应该承担“加载某个循环模板”的职责。角色配置切换时应加载完整 Profile，循环只是 Profile 的一个部分。旧脚本只作为流程样例，最终产品能力是通用的 Profile + 状态机 + observer/action slot。

## Logs / Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test -- src/__tests__/role-profile-templates.test.ts src/__tests__/profile-merge.test.ts`
- Browser check: 选择内置 `症状急速燃火` 后，循环编辑器显示 6 个阶段、1 个观察 Lane、1 个辅助 Lane，且没有手动模板入口。

## Risks

- 内置点位来自固定 UI 坐标，实际使用时仍需要按用户分辨率/UI 缩放重新取色校准。
- 当前角色 Profile 模板在前端创建保存；后续如果希望 CLI/后端也能初始化同样数据，需要把模板数据下沉为共享 JSON 资产。

## Next Step

把角色 Profile 模板继续做成可维护的数据资产，减少代码里硬编码技能/点位列表，并增加“重新取色校准当前角色 Profile”的工作流。
