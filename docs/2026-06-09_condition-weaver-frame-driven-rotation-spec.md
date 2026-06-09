# Condition Weaver Pistol/Dagger Frame-Driven Rotation Spec

## Goal

把 Snow Crows 页面、dps.report 日志和 AHK 的经验合并成一个可落地的循环设计：不按固定顺序硬跑，而是在每个 tick 读取当前 UI 帧，根据技能可用、元素协调状态、关键冷却和状态条结果决定下一次释放。

参考来源：

- Snow Crows: `Condition Weaver - Pistol & Dagger`, updated 2026-04-26
- dps.report: `https://dps.report/26i4-20260418-202046_golem`
- AHK 思路：用 `GetPixelColor(...)` 判定技能/点位状态，再触发 `SendLoop(...)`

## Core Decision

当前 Weaver preset 不能继续走“按 phase 顺序执行”。正确落地方式是：

1. 每 tick 采样一次屏幕快照。
2. 从快照中解析当前状态。
3. 用优先级规则选择一个技能。
4. 发送后等待“释放开始/释放完成/技能变黑/状态变更”之一确认。
5. 下一 tick 重新从当前帧判断，而不是假设上一步必然成功。

## Required Frame Signals

### 1. Skill Ready Signals

每个技能需要一个 ready 点位，默认用技能图标左上/冷却遮罩点。

| ID | Key | Purpose |
|---|---:|---|
| `weaver_weapon_1_ready` | 1 | 自动攻击填充 |
| `weaver_weapon_2_ready` | 2 | 当前元素下的 Pistol 2 |
| `weaver_weapon_3_ready` | 3 | 当前双元素 Dual Attack |
| `weaver_weapon_4_ready` | 4 | Dagger 4 |
| `weaver_weapon_5_ready` | 5 | Dagger 5 |
| `weaver_signet_fire_ready` | 8 | Signet of Fire |
| `weaver_signet_earth_ready` | 9 | Signet of Earth |
| `weaver_primordial_ready` | utility | Primordial Stance |
| `weaver_weave_self_ready` | 0 | Weave Self |

判断规则：

- `ready = pixel_skill_not_black(skill_id, tolerance)`
- `not_ready = pixel_skill_black(skill_id, tolerance)`
- 一个技能本 tick 只能被一个 lane 消费，避免主循环和辅助 lane 同时尝试。

### 2. Attunement State Signals

Weaver 必须独立确认元素协调状态，不能只靠“刚才按了 F1/F2/F3/F4”。

需要新增状态点位：

| Point ID | Meaning |
|---|---|
| `attune_fire_primary` | 当前主元素是 Fire |
| `attune_water_primary` | 当前主元素是 Water |
| `attune_air_primary` | 当前主元素是 Air |
| `attune_earth_primary` | 当前主元素是 Earth |
| `attune_fire_secondary` | 副元素是 Fire |
| `attune_water_secondary` | 副元素是 Water |
| `attune_air_secondary` | 副元素是 Air |
| `attune_earth_secondary` | 副元素是 Earth |

如果 UI 上无法稳定区分 primary/secondary，则退一步使用 F1-F4 图标的激活边框/高亮点位：

- `attune_fire_active`
- `attune_water_active`
- `attune_air_active`
- `attune_earth_active`

但这只能推断单元素，精度不如 primary/secondary。

解析结果统一写成：

```text
attunement_pair = fire | earth | air | water | fire_earth | earth_fire | air_earth | fire_air | water_earth | fire_water | unknown
```

### 3. Cast / Release Confirmation

优先用 ROI 施法条判断：

- `cast_bar_roi_border_visible` 表示施法开始。
- `cast_bar_roi_gone` 表示施法完成。
- 如果技能是瞬发，则允许用技能图标从 ready -> black 作为完成确认。

不同技能需要不同完成条件：

| Skill Type | Start Condition | Complete Condition |
|---|---|---|
| Attunement switch | key sent | target `attunement_pair` confirmed |
| Weapon attack | key sent or cast bar visible | skill icon black or cast bar gone |
| Instant utility | key sent | skill icon black |
| Auto attack | key sent | short timeout |
| Weave Self | key sent | elite icon black or cast bar gone |

## Runtime State

需要维护这些状态，但状态只作为辅助，不作为唯一真相：

```text
attunement_pair        // 每 tick 从点位解析
last_weave_self_ms     // Weave Self 最近释放时间
last_signet_fire_ms    // 8 最近释放时间
last_signet_earth_ms   // 9 最近释放时间
last_primordial_ms     // Primordial 最近释放时间
last_weapon4_ms        // 防止 4 重复抖动
last_weapon5_ms        // 防止 5 重复抖动
last_action_ms         // 全局技能间隔保护
weave_burst_mode       // 是否正在 Weave Self 爆发窗口
```

`attunement_pair` 每 tick 覆盖更新，不依赖 `post_actions` 盲写。

## Priority Model

每 tick 按以下顺序选择一个 action。

### P0: Safety / Lockout

如果满足任一条件，不发新技能：

- 当前已有 skill attempt 未完成。
- `cast_bar_roi_border_visible` 且技能不是可打断/瞬发。
- `now - last_action_ms < global_min_gap_ms`。
- 当前帧采样失败。

### P1: Confirm / Repair Attunement

如果下一条规则要求某个元素组合，但当前 `attunement_pair` 不匹配，先切元素。

切元素不是简单按键，而是：

```text
required_pair = target pair
if current pair already target:
  continue
else:
  press F1/F2/F3/F4 needed for next transition
  wait until target pair is confirmed by frame signal
```

举例：

- 需要 `earth_fire`，当前是 `fire`，按 F4。
- 需要 `fire_earth`，当前是 `earth`，按 F1。
- 需要 `dual_fire`，当前是 `earth_fire` 或 `fire_earth`，按 F1，直到确认 Fire primary/secondary 都是 Fire。

如果 900ms 内未确认目标 pair：

- 不推进循环。
- 重新采样。
- 最多重试一次。
- 仍失败则进入 `attunement_recover`，按当前目标 phase 重新切。

### P2: Weave Self Burst Entry

dps.report 里第一次 `Weave Self` 出现在约 71.719s，不是开场。这说明实际可落地配置不应该硬性开场 Weave Self。

进入条件建议：

```text
weaver_weave_self_ready == true
AND not currently casting
AND attunement_pair is earth or dual_earth or fire_earth
AND key priority lane has no immediately higher priority skill pending
```

进入后设置：

```text
weave_burst_mode = true
burst_step = 0
```

注意：如果用户想严格按 Snow Crows 页面开场，可以配置成 opener 模式；但按这份日志，默认应使用“可用后插入爆发段”。

### P3: High Priority Utility

这些技能不属于简单 phase 顺序，应作为可插入优先技能。

从 dps.report 可确认：

- `Signet of Fire`
- `Signet of Earth`
- `Primordial Stance`

规则：

```text
if signet_fire_ready and safe_to_cast:
  cast Signet of Fire

else if signet_earth_ready and safe_to_cast:
  cast Signet of Earth

else if primordial_ready and safe_to_cast:
  cast Primordial Stance
```

Snow Crows 页面同时提示 8、9、4、5 可用时尽快用，所以 8/9 不能只靠固定 timer，必须看 ready 点位。

### P4: Dagger Priority

日志中可识别的匕首技能：

- `Ring of Fire`
- `Fire Grab`
- `Churning Earth`
- `Earthquake`

它们应绑定到当前元素组合，而不是直接绑定 `weapon_4` / `weapon_5`。

建议配置：

```text
if attunement_pair includes fire and weapon4_ready:
  cast Ring of Fire

if attunement_pair includes fire and weapon5_ready:
  cast Fire Grab

if attunement_pair includes earth and weapon5_ready:
  cast Churning Earth

if attunement_pair includes earth and weapon4_ready:
  cast Earthquake
```

同一个按键在不同元素下对应不同技能语义，配置里应该拆成不同 skill slot：

- `weaver_fire_dagger_4_ring_of_fire`
- `weaver_fire_dagger_5_fire_grab`
- `weaver_earth_dagger_4_earthquake`
- `weaver_earth_dagger_5_churning_earth`

它们可以共享同一个 trigger key，但拥有不同的 `condition_expr`。

### P5: Weave Self Burst Rotation

爆发段不是按固定时间推进，而是按 step + frame 条件推进。

从 Snow Crows 页面抽象的 burst state list：

```text
earth       -> 0, 8, 2, 3
fire_earth  -> 5, 3
fire        -> 3, 2, 4
earth_fire  -> 2, 5
earth       -> 2, 3
air_earth   -> 8, 2, 3
fire_air    -> 2, 3, 4
fire        -> 3
earth_fire  -> 2, 3
earth       -> 3
water_earth -> 2, 3, 8, 5
fire_water  -> 3, 2
```

每个 step 执行前必须满足：

```text
current attunement_pair == step.required_pair
skill_ready(step.skill) == true
safe_to_cast == true
```

如果 skill 不 ready：

- 若该技能是核心技能 2/3：短暂等待一个 tick，不立刻跳过。
- 若超过 `step_wait_ms` 仍未 ready：进入 fallback，按 P3/P4/P6 选择其他技能。
- 若技能是 8/4/5：允许由 P3/P4 priority lane 提前消费，burst step 检测到已变黑后可标记 step done。

### P6: Normal Loop

普通 loop 也不按顺序硬跑，而是围绕当前 attunement pair 做条件选择。

建议主循环状态：

```text
fire       -> 3, 2
earth_fire -> 2, 3
earth      -> 3, 2
fire_earth -> 2, then fully attune fire
```

执行规则：

```text
if attunement_pair == fire:
  cast weapon3 if ready
  else cast weapon2 if ready
  else switch to earth when both key skills are consumed or not ready

if attunement_pair == earth_fire:
  cast weapon2 if ready
  else cast weapon3 if ready
  else switch/confirm earth

if attunement_pair == earth:
  cast weapon3 if ready
  else cast weapon2 if ready
  else switch to fire

if attunement_pair == fire_earth:
  cast weapon2 if ready
  then fully attune fire
```

这里的 `consumed` 不用盲计数，优先用技能图标变黑判定。

### P7: Auto Attack Fill

只有在以下情况才用 1：

```text
no P2/P3/P4/P5/P6 action is ready
AND not casting
AND global gap elapsed
```

这对应 Snow Crows 的 Fill gaps with Auto Attacks。

## Concrete Skill Conditions

### Attunement Switch

```text
cast F1/F2/F3/F4 only if:
  target pair is required
  current pair != target pair
  attunement key icon is not black
complete when:
  target attunement point(s) match
```

### Weave Self

```text
cast 0 only if:
  weaver_weave_self_ready
  safe_to_cast
  attunement_pair in [earth, dual_earth, fire_earth]
  not in burst mode
complete when:
  elite icon becomes black OR cast bar gone
post:
  weave_burst_mode = true
  last_weave_self_ms = now
```

### Signet of Fire / Signet of Earth

```text
cast if:
  skill ready
  safe_to_cast
  not blocking an attunement repair
complete when:
  skill icon becomes black
```

### Primordial Stance

```text
cast if:
  skill ready
  safe_to_cast
  current attunement_pair includes fire or earth
complete when:
  skill icon becomes black
```

### Weapon 2 / Weapon 3

```text
cast if:
  current attunement_pair matches the loop/burst step
  skill ready
  safe_to_cast
complete when:
  skill icon black OR cast bar gone
```

### Dagger 4 / Dagger 5

```text
cast if:
  current attunement_pair includes expected element
  skill ready
  safe_to_cast
  not consumed in the current burst step
complete when:
  skill icon black OR cast bar gone
```

## What Needs To Change In Current Config

### 1. Split Generic Weapon Slots

Current:

```text
weaver_weapon_2
weaver_weapon_3
weaver_weapon_4
weaver_weapon_5
```

Should become semantic skills:

```text
weaver_fire_pistol_2
weaver_earth_pistol_2
weaver_fire_earth_dual_3
weaver_earth_fire_dual_3
weaver_air_earth_dual_3
weaver_fire_air_dual_3
weaver_water_earth_dual_3
weaver_fire_water_dual_3
weaver_fire_dagger_4_ring_of_fire
weaver_fire_dagger_5_fire_grab
weaver_earth_dagger_4_earthquake
weaver_earth_dagger_5_churning_earth
```

这些 skill 可共享按键和像素坐标，但条件不同。

### 2. Add Attunement Point Model

需要新增点位组：

```text
attune_fire_primary
attune_water_primary
attune_air_primary
attune_earth_primary
attune_fire_secondary
attune_water_secondary
attune_air_secondary
attune_earth_secondary
```

并新增表达式能力或组合表达式模板：

```text
attunement_pair_is("earth_fire")
```

可以先用 `and(pixel_point(...), pixel_point(...))` 表达。

### 3. Move From Phase-Only To Priority Scheduler

当前 phase 模型可以保留，但 Weaver 应该配置成：

- `repair_attunement_lane`
- `weave_self_burst_lane`
- `priority_utility_lane`
- `dagger_priority_lane`
- `normal_loop_lane`
- `auto_attack_lane`

每个 lane 根据优先级抢占，但同 tick 只执行一个技能。

### 4. Use dps.report As Calibration

这份日志显示：

- 第一次 `Weave Self` 在 `71.719s`
- `Signet of Fire` 大约每 10-11s 出现
- `Signet of Earth` 大约每 12-13s 出现
- `Primordial Stance` 多次插入
- 常规 attunement pattern 大量重复 `Fire/Earth` 与 `Earth/Fire`

所以默认策略应是：

```text
normal_loop first
weave_self when ready and safe
return to normal_loop after burst
```

而不是开场硬进入 Weave Self。

## Landing Plan

### Step 1

先做取色资产：

- 增加 attunement primary/secondary 点位。
- 增加 8/9/0 与 weapon 2/3/4/5 的 ready 点位。

### Step 2

改 Weaver seed：

- 删除或弱化 generic `weaver_weapon_2` 语义。
- 新增 semantic skills，共享按键和像素。

### Step 3

改 Weaver cycle preset：

- 从当前顺序 phase 改为 priority lane 风格。
- 每个 skill slot 都带 attunement condition。

### Step 4

增加校验：

- semantic skill 必须有 attunement condition。
- attunement switch 必须有 target pair complete condition。
- Weaver profile 不允许 `complete_expr = pixel_skill_black(attunement skill)` 作为唯一确认条件。

## Current Verdict

当前 `condition_weaver_pistol_dagger` preset 只能作为 Snow Crows 页面草稿。

要达到可实战落地，必须改为：

```text
frame signals -> attunement pair -> priority rules -> one action per tick -> release confirmation -> next frame
```

这和 AHK 的核心思路一致：不是相信脚本顺序，而是每次都看当前帧状态。
