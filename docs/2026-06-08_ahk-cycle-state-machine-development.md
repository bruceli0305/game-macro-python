# AHK 循环状态机开发文档

## Goal

把 `ahk/` 下两个旧 AHK 循环迁移为 Tauri/Vue/Rust 项目的可视化状态机能力。

本项目不复刻 AHK 的 `SendLoop` 连续发键模式。新的执行模型必须表达真实意图：

- 先通过像素、运行状态或技能指标判断技能是否就绪。
- 一个技能尝试只发送一次按键。
- 等待释放开始证据，例如状态条变化。
- 等待释放完成证据，例如状态条结束、图标进入冷却或固定兜底时间。
- 通过 marker、timer、counter 记录运行时状态。
- 由调度器决定下一技能或下一阶段。

## Development Principles

- `models/` 只放可序列化数据模型，不写业务逻辑。
- `ast/` 保持纯逻辑，不依赖 Tauri、tokio、文件 I/O 或输入输出副作用。
- `engine/` 负责执行决策、状态机和调度。
- `commands/` 只做 IPC 薄层、参数校验和服务转发。
- 前端页面不直接调用 `invoke()`，通过 composables 封装。
- 不暴露原始连发次数作为用户功能。
- 持久化模型变更必须同步 Rust 类型、TypeScript 类型、校验、测试和文档。

## Current Baseline

已存在能力：

- `CycleConfig` / `CyclePhase` / `SkillSlot`
- 阶段完成模式
- 技能槽优先级
- `condition_expr`
- `start_expr`
- `complete_expr`
- 技能冷却与弹药阶段像素
- `SkillAttemptExecutor`
- `CycleExecutor`
- runtime skill metrics
- simulator debug 输出
- profile 保存与启动校验

## Implemented In This Pass

### Attempt Policy

- 新增持久化 `SkillSlot.attempt_policy`。
- `CycleExecutor` 支持每个技能槽覆盖全局尝试策略。
- `max_attempts` 解释为总尝试次数，`1` 表示只发送一次按键。
- 支持每槽覆盖：
  - `start_timeout_ms`
  - `complete_timeout_ms`
  - `retry_delay_ms`
  - `failure_policy`
  - `complete_fallback`
- Rust 回归测试覆盖：
  - 单次尝试不连发。
  - 完成超时策略按槽覆盖。

### Detection Templates

- `ConditionBuilder` 支持 `cast_bar_changed`。
- 技能槽编辑器提供释放开始和释放完成模板。
- 新增 detection template 工具函数与前端测试。

### Runtime Timers

- `CycleConfig.state_schema.timers`
- `RuntimeAction`:
  - `record_timer`
  - `reset_timer`
- AST:
  - `timer_elapsed_ge`
  - `timer_elapsed_lt`
- `RuntimeState` 实现 `TimerProvider`。
- `CycleExecutor` 支持阶段入口动作与技能成功后动作。
- 前后端校验覆盖 timer 声明、表达式引用和动作引用。
- 编辑器支持 timer 声明、timer 条件和 post action。

### Runtime Markers

- `CycleConfig.state_schema.markers`
- `RuntimeAction`:
  - `set_marker`
  - `clear_marker`
- AST:
  - `marker_eq`
  - `marker_ne`
- `RuntimeState` 实现 `MarkerProvider`。
- 前后端校验覆盖 marker 声明、允许值、表达式引用和动作引用。
- 编辑器支持 marker 声明、marker 条件和 post action。

### Runtime Counters

- `CycleConfig.state_schema.counters`
- `RuntimeCounterDef`:
  - `id`
  - `name`
  - `initial_value`
  - `reset_on_phase_entry`
  - `reset_on_cycle_start`
- `RuntimeAction`:
  - `increment_counter`
  - `set_counter`
  - `reset_counter`
- AST:
  - `counter_ge`
  - `counter_eq`
  - `counter_gt`
- `RuntimeState` 实现 `CounterProvider`。
- `CycleExecutor` 支持：
  - 初始化 counter 初始值。
  - 阶段进入时按 schema 重置 counter。
  - cycle reset 时按 schema 重置 counter。
  - 技能成功后执行 counter post action。
- 前后端校验覆盖 counter 声明、表达式引用和动作引用。
- 编辑器支持：
  - 在运行状态面板声明 counter。
  - 在条件构建器中选择 counter 条件。
  - 在技能 post action 中增加、设置、重置 counter。
- Rust 回归测试覆盖 counter post action 门控后续阶段技能。

### Phase Transitions

- `CyclePhase` 新增 `transition_rules` 和 `fallback_transition`。
- `PhaseTransitionRule` 支持 `label`、`condition_expr` 和 `target_phase`。
- `PhaseFallbackTransition` 支持：
  - `stay`
  - `next`
  - `phase`
- `CycleExecutor` 在阶段完成后按顺序求值 transition rules。
- rule 命中后跳转到命名阶段；未命中时执行 fallback。
- 未配置 fallback 的旧 profile 继续保持进入下一阶段。
- transition 求值复用现有 AST evaluator 和 runtime providers。
- 后端保存校验覆盖 transition/fallback 目标阶段和条件表达式引用。
- 前端保存校验覆盖 transition/fallback 目标阶段。
- 编辑器在 phase 下方新增「阶段跳转规则」区域。
- Rust 回归测试覆盖 rule 命中后跳过默认下一阶段并跳到指定阶段。

### Simulator Presentation

- 模拟结果表格将 `phase_transition` 展示为「阶段跳转」。
- `Applied` 结果展示为「已应用」，不再被统计为失败。
- summary 增加 transition 计数。
- top reasons 和事件表格复用统一中文原因翻译。
- 时间线在没有技能 ID 的事件上显示事件标签，避免阶段跳转空白。

### Pixel Condition Templates

- AST 新增：
  - `pixel_point_not_match`
  - `pixel_point_black`
  - `pixel_point_not_black`
  - `pixel_skill_not_match`
  - `pixel_skill_black`
  - `pixel_skill_not_black`
- evaluator 支持 match、not-match、black、not-black 四类像素谓词。
- black / not-black 使用 `tolerance` 作为黑色阈值。
- compiler、probe collection、前后端引用校验均已同步。
- ConditionBuilder 支持创建这些像素条件。
- SkillCard 能显示这些像素条件摘要。
- 完成检测模板新增「技能图标变黑」。

## Current Data Model

### CycleStateSchema

```ts
interface CycleStateSchema {
  markers: RuntimeMarkerDef[];
  timers: RuntimeTimerDef[];
  counters: RuntimeCounterDef[];
}

interface RuntimeMarkerDef {
  id: string;
  name: string;
  initial_value: string;
  allowed_values: string[];
}

interface RuntimeTimerDef {
  id: string;
  name: string;
  reset_on_cycle_start: boolean;
}

interface RuntimeCounterDef {
  id: string;
  name: string;
  initial_value: number;
  reset_on_phase_entry: boolean;
  reset_on_cycle_start: boolean;
}
```

### RuntimeAction

```ts
type RuntimeAction =
  | { type: "set_marker"; marker_id: string; value: string }
  | { type: "clear_marker"; marker_id: string }
  | { type: "record_timer"; timer_id: string }
  | { type: "reset_timer"; timer_id: string }
  | { type: "increment_counter"; counter_id: string; by: number }
  | { type: "set_counter"; counter_id: string; value: number }
  | { type: "reset_counter"; counter_id: string };
```

### Added AST Nodes

```ts
type Expr =
  | { type: "marker_eq"; marker_id: string; value: string }
  | { type: "marker_ne"; marker_id: string; value: string }
  | { type: "timer_elapsed_ge"; timer_id: string; ms: number }
  | { type: "timer_elapsed_lt"; timer_id: string; ms: number }
  | { type: "counter_ge"; counter_id: string; value: number }
  | { type: "counter_eq"; counter_id: string; value: number }
  | { type: "counter_gt"; counter_id: string; value: number };
```

## Editor Surface

### CycleEditorPage

- 顶层提供「运行状态」面板。
- 用户可声明：
  - 标记
  - 时间标记
  - 计数器
- 阶段列表继续使用当前主循环单 lane 模型。

### ConditionBuilder

当前支持：

- AND / OR / NOT
- 技能像素匹配
- 点位像素匹配
- 状态条变化
- 技能指标达到
- 标记等于 / 不等于
- 时间标记已超过 / 未超过
- 计数器大于等于 / 等于 / 大于
- 恒真 / 恒假

### SkillEditModal

当前支持：

- 基础技能槽字段。
- 就绪条件、释放开始检测、释放完成检测。
- 每槽失败与重试策略。
- 技能成功后的 post actions：
  - 设置标记
  - 清除标记
  - 记录时间标记
  - 重置时间标记
  - 增加计数
  - 设置计数
  - 重置计数

## Remaining Work

### Phase Transitions

Status:

- 基础 model、校验、executor 跳转行为、编辑器 UI 和回归测试已完成。
- runtime log 会产生 `phase_transition` 事件，reason 包含命中的 rule 或 fallback。
- simulator/debug 面板还需要把该事件整理成更友好的中文说明。

### Assist Lanes

Status:

- 已完成配置前置设计和编辑器表达。
- `CycleConfig` 新增 `assist_lanes`，主 lane 仍使用现有 `phases`。
- assist lane 字段包括 `id`、`name`、`enabled`、`check_interval_ms`、`interrupt_policy`、`skills`。
- interrupt policy 当前支持：
  - `idle_only`：仅主循环空闲时允许检查，默认值。
  - `complete_wait`：允许在主 lane 等待释放完成时检查。
  - `any_wait`：允许任意等待期检查。
- 编辑器新增“辅助 Lane”面板，可配置 lane、添加技能槽并复用现有技能槽弹窗。
- frontend save validation 与 backend profile command validation 已覆盖 assist lane 的 ID、名称、检查间隔、打断策略、技能引用、AST 引用和 post actions。
- `CycleExecutor` 已消费 `assist_lanes`：
  - main lane 优先扫描。
  - main 没有 ready slot 时，assist lane 可按 `check_interval_ms` 扫描并执行。
  - `idle_only` 不会插入主 lane pending attempt。
  - `complete_wait` 可在主 lane 完成等待期插入 assist attempt。
  - `any_wait` 可在主 lane start/retry/complete 等待期插入 assist attempt。
- assist attempt 复用同一套技能尝试状态机，并共享 cooldown、runtime state、post actions 和执行日志。
- `SkillSlot.protected_release` 已实现：
  - 编辑器技能槽弹窗可配置“保护释放”。
  - 技能卡片摘要会显示保护释放状态。
  - main lane pending attempt 开启保护时，assist lane 即使配置 `complete_wait` / `any_wait` 也不会插入。

尚未完成：

- assist scheduler 目前是单 pending attempt 插入模型，不是多 lane 真并发。

### Pixel Condition Templates

Status:

- 基础 AST、求值、校验、ConditionBuilder 模板和完成检测模板已完成。
- 后续可继续补更细的模板分组和高级说明。

### Presets

Status:

- 已新增前端内置手工 preset 工具 `src/utils/cycle-presets.ts`。
- 已在循环编辑器顶部新增“选择模板 / 应用模板”入口。
- 已完成两个 AHK 派生模板：
  - 直伤大剑灵刃：6 个主 lane phase，包含 `weapon` marker、`last_main_burst` / `last_entry_swap` timer，以及主/副武器计数器。
  - 症状急速燃火：6 个主 lane phase，1 个 assist lane，包含 F1、火炬、武器刷新和辅助技能节流 timer。
- 两个模板均显式标记关键技能槽的 `protected_release`。
- 模板只表达状态机结构和占位技能 ID，不导入 AHK、不自动创建技能库或点位；用户仍需要在技能管理中补齐实际技能、按键和像素。

仍不实现任意 AHK 自动导入。

## Verification

本轮已验证：

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`：59 passed
- `cargo check --all-targets`
- `cargo fmt --all -- --check`
- `cargo test`：151 passed
- `cargo clippy --all-targets -- -D warnings`
- `pnpm.cmd build`
- 浏览器烟测：`/cycle-editor` 可加载，技能槽弹窗可打开，条件类型下拉可展示新增像素条件。
- 浏览器烟测：辅助 Lane 面板可渲染，添加 lane 后显示默认 `idle_only` 策略和添加技能入口。
- 浏览器烟测：辅助 Lane 面板已显示“执行时按检查间隔和打断策略调度”的 scheduler 文案。
- 浏览器烟测：技能槽弹窗可显示“保护释放”开关和禁止辅助 Lane 插入提示。
- 浏览器烟测：`/cycle-editor` 可显示“选择模板 / 应用模板”，下拉包含“直伤大剑灵刃”和“症状急速燃火”。
- 浏览器烟测：应用“症状急速燃火”后页面显示 6 个阶段、1 个辅助 lane、17 个技能槽，辅助 lane id/name/check interval 分别为 `firebrand_mantra_assist`、`咒语/补充技能辅助 Lane`、`250`。

## Risks

- marker、timer、counter 的重置策略必须在 UI 中保持清晰，否则用户容易配置出粘滞状态。
- phase transition 一旦加入，会改变当前顺序推进语义，必须优先补 executor 单测。
- assist lane 已能插入主等待期；关键释放必须在 preset 或用户配置中显式开启 protected release。
- 像素黑/非黑模板需要明确容差，否则不同显示器下会不稳定。

## Next Step

下一开发切片建议：

1. 清理现有中文文案编码显示问题，优先处理辅助 Lane、运行控制、技能槽统计等用户可见区域。
2. 为两个 preset 增加“技能映射向导”，让占位技能 ID 绑定到用户已有技能配置，而不是要求用户手工逐项替换。
3. 后续再评估多 lane 真并发是否必要。
