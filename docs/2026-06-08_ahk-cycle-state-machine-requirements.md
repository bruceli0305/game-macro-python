# AHK 循环状态机需求文档

## Goal

把 `ahk/` 下两个旧脚本的循环逻辑沉淀为新项目的编辑器和引擎需求。

新系统不应提供这种用户配置方式：

```ahk
loop 10 {
  SendLoop(wp4key, 69)
}
```

这种写法本质是旧脚本用定时和连发掩盖状态不可见。新系统应使用状态机：

1. 检查技能是否就绪。
2. 一个 attempt 只发送一次按键。
3. 等待释放开始证据。
4. 等待释放完成证据。
5. 标记 attempt 为 success、failed 或 not ready。
6. 由 scheduler 决定下一技能或阶段。

## Source AHK Files

- `ahk/直伤大剑灵刃.ahk`
- `ahk/急速燃.ahk`
- `ahk/config/成小林直伤灵刃.ini`
- `ahk/config/成小林症状急速燃.ini`

当前仓库中的 AHK 文件名可能存在编码显示问题，实际分析以 `ahk/` 目录内容为准。

## Existing AHK Behavior Summary

### Common Mechanics

- 技能就绪主要来自屏幕像素：
  - `wp*`：主武器技能。
  - `twp*`：副武器或切换后武器技能。
  - `ty*`：通用技能。
  - `f*`：职业技能。
  - `point*`：特殊状态点。
  - `qwq`：武器切换可用状态。
- AHK 基本使用严格颜色相等。
- 脚本混用发键、sleep、Gosub 和全局变量。
- 全局变量表达运行状态，例如 `a`、`b`、`c`、`d`、`currentWeapon`、`lastKeyTime*`。
- 部分逻辑是主循环阶段，部分逻辑是后台辅助 lane。

### Direct Power Greatsword Virtuoso

该脚本更接近单 lane 阶段状态机：

- 启动时根据武器像素进入不同阶段。
- `a4`、`b1`、`b2`、`b3` 互相跳转。
- `a`、`b`、`c`、`d` 计数器控制爆发或切武器条件。
- `lastKeyTime`、`lastKeyTime2` 等 timer 避免爆发段过快重复。

迁移要求：

- 使用 phase 表达 `a4`、`b1`、`b2`、`b3`。
- 使用 counter 表达 `a`、`b`、`c`、`d`。
- 使用 timer 表达 `lastKeyTime*`。
- 使用 marker 表达当前武器。
- 使用 transition rules 替代 `Gosub`。

### Condition Quickness Firebrand

该脚本包含两条逻辑 lane：

- `a1`：主输出循环。
- `a2`：后台辅助/咒语补放循环。

主 lane 使用：

- `currentWeapon` 判断主/副武器。
- `lastKeyTime*` 控制定时刷新。
- `point0` 等特殊点位判断 F1 或后续状态。

辅助 lane 使用：

- `ty2` / `ty3` 非黑检查，带 1 秒节流。
- `point3` / `point4` 触发 `ty1`，同样带节流。

迁移要求：

- 主输出保留在 main lane。
- 后台补放应进入 assist lane。
- assist lane 必须遵守 interrupt policy，默认不得打断受保护释放。

## Design Principle

AHK 连发不是需求本身。它通常表示以下意图之一：

- 等待释放开始。
- 等待技能图标变化。
- 覆盖输入延迟。
- 持有阶段直到条件变化。
- 近似释放或后摇时间。

新系统应把这些意图显式建模，而不是继续暴露裸连发。

## Required Engine Capabilities

### Current Implementation Status

已完成基础能力：

- 技能 attempt policy。
- 释放开始检测和释放完成检测。
- 有限 retry，不使用裸 key spam。
- runtime timers：
  - schema
  - AST condition
  - runtime action
  - validation
  - executor tests
- runtime markers：
  - schema
  - AST condition
  - runtime action
  - validation
  - executor tests
- runtime counters：
  - schema
  - AST condition
  - runtime action
  - validation
  - executor tests
  - editor declaration and post-action UI
- conditional phase transitions：
  - model
  - AST condition evaluation
  - target validation
  - executor jump behavior
  - editor transition rows
  - executor tests
- simulator/debug presentation for phase transitions
- pixel condition templates：
  - match
  - not match
  - black
  - not black
- assist lanes：
  - data model
  - validation
  - editor panel
  - executor scheduling
  - protected release interrupt guard
- AHK preset profiles：
  - 直伤大剑灵刃
  - 症状急速燃火
  - editor apply entry

仍待实现：

- 技能映射向导：把 preset 占位技能 ID 绑定到用户已有技能。

### 1. Skill Attempt State Machine

状态机应覆盖：

- `ready_check`
- `preparing`
- `key_sent`
- `start_wait`
- `casting`
- `complete_wait`
- `success`
- `failed`
- `skipped_not_ready`

要求：

- 每次 attempt 只发一次键。
- retry 必须重新进入 attempt state machine。
- timeout 和 fallback 必须可配置并可校验。

### 2. Cast-Bar Based Start Detection

每个技能槽应支持 start condition。

示例：

- 状态条发生变化。
- 状态条像素匹配 active color。
- 技能图标在发键后变化。
- 没有视觉证据时才使用固定时间兜底。

编辑器要求：

- 使用「释放开始检测」替代 raw `Start Expr`。
- 提供常用模板。

### 3. Completion Detection

每个技能槽应支持 complete condition。

示例：

- 状态条回到 idle。
- 技能图标进入冷却。
- 技能图标变黑或不可用。
- 特定点位发生变化。
- 固定读条时间兜底。

编辑器要求：

- 使用「释放完成检测」替代 raw `Complete Expr`。
- 提供常用模板。

### 4. Retry Policy Without Key Spam

字段：

- `max_attempts`
- `retry_delay_ms`
- `start_timeout_ms`
- `complete_timeout_ms`
- `failure_policy`
- `complete_fallback`

规则：

- retry 是新的状态机 attempt。
- 不能把 retry 表达成一个隐藏的 key repeat loop。

### 5. Runtime Markers

用途：

- 表达离散状态，例如当前武器或 F1 状态。

例子：

- `weapon = main`
- `weapon = alternate`
- `f1_state = open`

需要：

- 声明 marker。
- 设置 marker。
- 清除 marker。
- 在条件中比较 marker。
- 保存和启动前校验 marker 引用。

### 6. Runtime Timers

用途：

- 表达“距离某事件过去多久”。

例子：

- `last_f1_burst >= 8000ms`
- `last_torch4 >= 3000ms`
- `last_wp5_refresh >= 17000ms`
- `last_wp4_refresh >= 13000ms`

需要：

- 声明 timer。
- 记录当前时间。
- 重置 timer。
- 在条件中比较 elapsed time。
- 保存和启动前校验 timer 引用。

### 7. Runtime Counters

用途：

- 表达阶段内或循环内的命中次数、已见状态、爆发门槛。

例子：

- `main_wp4_count > 0`
- `main_wp2_count >= 2`
- `alt_twp5_seen > 0`
- `alt_twp3_seen > 0`

需要：

- 声明 counter。
- 增加 counter。
- 设置 counter。
- 重置 counter。
- 可配置阶段进入或 cycle reset 时重置。
- 在条件中比较 counter。
- 保存和启动前校验 counter 引用。

### 8. Conditional Phase Transition

AHK 的 `Gosub b1/b2/b3/a4` 应替换为显式 transition rules。

模型要求：

- Phase 有有序 transition rules。
- 每条 rule 包含：
  - label
  - condition expression
  - target phase
- Phase 有 fallback：
  - stay
  - next
  - named phase

执行要求：

- phase complete 后按顺序检查 transition rules。
- 命中 rule 后跳转到目标 phase。
- 未命中时执行 fallback。
- simulator/debug log 必须说明命中的 rule 或 fallback。

编辑器要求：

- 在 phase 下方显示 transition rows。
- target phase 使用选择器，不让用户手写不稳定 ID。
- 保存时校验 target phase 是否存在。

当前状态：

- 基础闭环已实现。
- simulator/debug log 已有 `phase_transition` 事件。
- 面向用户的 simulator 说明展示仍需下一步整理。

### 9. Background Assist Lane

Quickness Firebrand 的 `a2` 不应硬塞到主 phase 列表。

lane 模型要求：

- `main` lane：主循环，负责主要输出顺序。
- `assist` lane：轻量辅助动作，按 throttle 检查。
- assist lane 与 main lane 共享 runtime state。
- interrupt policy 控制能否在主 lane 释放等待中插入动作。
- 当前数据结构采用 `CycleConfig.phases` 表达 main lane，`CycleConfig.assist_lanes` 表达后台辅助 lane。
- 当前 editor 已能配置 assist lane 的启用状态、检查间隔、interrupt policy 和技能槽。
- 当前 executor 已消费 assist lane，并按 lane 检查间隔调度后台技能。
- assist 执行日志使用 `assist_execute` / `assist_skip` 事件。

默认约束：

- 不允许打断主 lane 受保护释放。
- assist skill 仍然走同一套 attempt state machine。
- `SkillSlot.protected_release` 已用于显式保护主 lane 关键释放；开启后 assist lane 不会在该技能 pending attempt 期间插入。

### 10. Pixel Condition Templates

AHK 里有 exact color、not match、black、not black 等条件。

需要模板：

- 技能像素匹配配置颜色。
- 技能像素不匹配配置颜色。
- 点位像素匹配配置颜色。
- 点位像素不匹配配置颜色。
- 技能像素黑。
- 技能像素非黑。
- 点位像素黑。
- 点位像素非黑。

要求：

- 默认用户不需要编辑 raw AST JSON。
- 高级 JSON/AST 视图可以后续保留给高级用户。

当前状态：

- 基础 AST、求值、引用校验和 ConditionBuilder 模板已实现。
- 完成检测模板已支持「技能图标变黑」。
- 后续可继续补模板分组说明和更细的默认容差提示。

## Suggested Editor Structure

### Cycle Level

「运行状态」面板：

- Markers
- Timers
- Counters

### Phase Level

每个 phase 展示：

- phase name。
- completion mode。
- entry actions。
- transition rules。
- fallback transition。

### Slot Level

技能槽编辑器分区：

1. 基础
2. 释放条件
3. 释放检测
4. 失败与重试
5. 执行后动作

Skill card 摘要展示：

- readiness condition。
- start/complete detection。
- retry policy。
- post action chips。

## Migration Shape

### Direct Power Greatsword Virtuoso

建议主 lane phases：

1. 入口判定
2. 副武器起手
3. 主武器循环
4. 副武器循环
5. 主武器起手修正
6. 切武器爆发

需要 runtime state：

- marker:
  - `weapon`
- timers:
  - `last_main_burst`
  - `last_entry_swap`
- counters:
  - `main_wp4_count`
  - `main_wp2_count`
  - `alt_twp5_count`
  - `alt_twp3_count`

### Condition Quickness Firebrand

建议 lanes：

- main lane。
- assist lane。

main lane phases：

1. 常规优先级
2. F1 打开处理
3. 主武器循环
4. 火炬循环
5. 切武器处理
6. 定时刷新 wp4/wp5

assist lane：

1. 咒语补放

需要 runtime state：

- marker:
  - `weapon`
- timers:
  - `last_f1_burst`
  - `last_torch4`
  - `last_wp5_refresh`
  - `last_wp4_refresh`
  - `last_ty2_assist`
  - `last_ty3_assist`
  - `last_ty1_assist`

## Implementation Order

1. 编辑器文案和释放检测模板。
2. per-slot attempt policy。
3. runtime timers。
4. runtime markers。
5. runtime counters。
6. conditional phase transitions。
7. assist lanes。
8. AHK preset profiles。

当前已完成 1-8：`assist_lanes` 数据结构、保存校验、编辑器面板、executor 调度基础、protected release、simulator/debug 事件展示，以及两个手工 AHK 派生 preset。preset 只提供状态机结构和占位技能 ID，不做任意 AHK 自动导入。

## Non-Goals

- 不实现裸 key-spam loop 作为用户功能。
- 不读取游戏内存。
- 不注入游戏进程。
- 不创建隐藏 AHK 兼容层。
- 不用递归调用模拟 AHK `Gosub`。
- 当前阶段不做任意 AHK 自动导入。

## Open Questions

- cast-bar detection 应全局复用还是每个 skill slot 独立配置？
- post-actions 是否需要支持 `key_sent`、`cast_started`、`success`、`failed` 多个触发时机？
- black/non-black 检测的默认容差应该是多少？
- counter 重置策略是否还需要 phase exit？
