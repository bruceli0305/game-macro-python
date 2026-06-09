# AHK 循环规格与多角色配置计划

## Goal

把 `ahk/` 下面两套固定脚本拆解为本项目的状态机配置规格，并明确后续是否需要多角色配置。

本项目不需要做通用 AHK 导入器。原因是当前只有两套明确脚本，正确路线是人工梳理循环语义，再按新引擎的数据模型配置，而不是把旧脚本的过程式写法直接搬进来。

## Source

- `ahk/直伤大剑灵刃.ahk`
- `ahk/急速燃.ahk`
- `ahk/config/成小林直伤灵刃.ini`
- `ahk/config/成小林症状急速燃.ini`

## Overall Decision

### 1. 不做 AHK/INI 通用导入器

固定两套脚本不值得做通用导入器。INI 里的按键、坐标和颜色可以作为手工建模输入，但最终应该沉淀成项目自己的 Profile 数据。

需要做的是：

- 拆解两个 AHK 的循环状态。
- 把旧变量映射到 `marker`、`timer`、`counter`。
- 把像素判断映射到 AST 条件。
- 把 `SendLoop` 语义改造为技能尝试状态机，不复刻按键连发。

### 2. 需要多角色配置

这两套脚本差异不只是循环顺序，还包括：

- 按键绑定不同。
- 点位坐标不同。
- 技能颜色不同。
- 循环状态机不同。
- 施法条 ROI 参数可能不同。

因此不应该在单个 Profile 内混放。更合理的边界是：

```text
角色配置 = base + skills + points + rotation + state_schema
```

后续需要把当前硬编码的 `default` Profile 改成可选择的 active Profile。

## Current Project Fit

### 已满足

- 技能/点位像素匹配、不匹配、黑色、非黑。
- 施法条 ROI 条件：变化、边框出现、消失。
- Phase + 优先级技能槽。
- Assist Lane。
- Marker / Timer / Counter。
- Phase transition rules。
- 技能 `start_expr` / `complete_expr`。
- 成功后执行 `post_actions`。

### 不足

1. 当前引擎只加载 `default` Profile 的第一个 rotation。
2. 当前编辑器也只编辑 `rotations[0]`，保存时会用单个 rotation 覆盖。
3. 缺少 active Profile 概念。
4. 缺少条件动作槽：条件命中后只执行 runtime actions，不发技能。
5. 缺少手工沉淀后的两套 AHK 状态机配置。

## 直伤大剑灵刃

### AHK 结构

- `startrun`: 启停主线程，只启动 `a1`。
- `a1`: 初始化计数器和 timer，然后根据当前武器像素进入状态。
- `a4`: 副武器且可切武器时的阶段。
- `b1`: 主武器阶段。
- `b2`: 副武器阶段。
- `b3`: 主武器起手阶段。
- `a2`: 代码存在，但 `startrun` 未启动，不作为主迁移目标。

### 状态机映射

| AHK label | 新模型 | 说明 |
|---|---|---|
| `a1` | bootstrap phase | 初始化状态并选择目标 phase |
| `a4` | phase: alt_ready_switch | 副武器状态，满足 `qwq` 后进入爆发链 |
| `b1` | phase: main_weapon | 主武器循环 |
| `b2` | phase: alt_weapon | 副武器循环 |
| `b3` | phase: main_opener | 主武器起手 |

### 变量映射

| AHK 变量 | 新模型 | 说明 |
|---|---|---|
| `a` | counter | 副武器 5 号已参与爆发 |
| `b` | counter | 副武器 3 号已参与爆发 |
| `c` | counter | 主武器 4 号计数 |
| `d` | counter | 主武器 2 号计数 |
| `lastKeyTime` | timer | 爆发段节流，AHK 中有 9457ms 条件 |
| `lastKeyTime2` | timer | `qwq` 切换节流，AHK 中有 4012ms 条件 |

### 迁移要点

- `Gosub a4/b1/b2/b3` 应改成 phase transition，不保留过程式跳转。
- `a/b/c/d` 应改成 counter，并通过技能成功后的 post action 更新。
- `lastKeyTime*` 应改成 timer，并通过 post action 记录。
- `SendLoop(wp4key, 10)` 这类“直到图标变黑”的循环，应改成：
  - 技能槽 condition: 图标非黑或匹配。
  - start detection: ROI 或技能像素变化。
  - complete detection: 技能图标变黑 / 施法条消失。
  - attempt timeout + retry policy。

## 急速燃

### AHK 结构

- `startrun`: 同时启动 `a1` 和 `a2`。
- `a1`: 主输出循环。
- `a2`: 后台 watcher，只做条件检测与 timer 刷新。

### 主循环状态

`a1` 没有 label 间跳转，而是依赖 `currentWeapon` 和多个 timer 控制分支。

| AHK 状态 | 新模型 | 说明 |
|---|---|---|
| `currentWeapon = wp2` | marker `weapon = wp2` | 主循环认为当前在 wp2 路径 |
| `currentWeapon = twp` | marker `weapon = twp` | 由 `wp5` 分支写入 |
| `currentWeapon = twp2` | marker `weapon = twp2` | 由 `twp4`、`twp5`、`point5`、`qwq` 分支写入 |

### Timer 映射

| AHK 变量 | 新模型 | AHK 条件 |
|---|---|---|
| `lastKeyTime` | timer `burst_f1` | `>= 8000` |
| `lastKeyTime1` | timer `twp4_gate` | `>= 3000` |
| `lastKeyTime2` | timer `ty2_seen` | `>= 1000`，由 `a2` 更新 |
| `lastKeyTime3` | timer `ty3_seen` | `>= 1000`，由 `a2` 更新 |
| `lastKeyTime4` | timer `point3_seen` | `>= 1000`，由 `a2` 更新 |
| `lastKeyTime5` | timer `point4_seen` | `>= 1000`，由 `a2` 更新 |
| `lastKeyTime6` | timer `point2_periodic` | `>= 17000` |
| `lastKeyTime7` | timer `point1_periodic` | `>= 13000` |

### 后台 watcher

`a2` 的关键特点是条件命中后不一定发键：

```ahk
SendLoop(ty2key,0)
SendLoop(ty3key,0)
lastKeyTime2 := A_TickCount
```

`SendLoop(..., 0)` 实际不发送按键。迁移后不应该建假技能，而应该建“条件动作槽”：

```text
condition_expr -> runtime_actions(record_timer)
```

建议新增：

- `ActionSlot` 或 `ObserverSlot`。
- 可放在 Assist Lane 中。
- 条件成立时执行 runtime actions。
- 不参与技能发键、不占用 protected release。

### 迁移要点

- `a1` 是 main lane。
- `a2` 是 observer lane，不是普通技能辅助 lane。
- `currentWeapon` 必须转为 marker。
- `point1/point2` 的周期爆发应转为 timer gated phase/slot。
- `point0` 起手块可以作为优先级最高的一组条件技能槽。

## 多角色配置方案

### 目标

支持用户在 UI 中维护多套角色配置，并选择当前运行的角色。

### 数据模型

保持现有 Profile 文件结构，增加 active profile 选择，而不是先做多 rotation 编辑。

建议：

```text
profiles/
  default/
    profile.toml
  power_greatsword_virtuoso/
    profile.toml
  condition_quickness_firebrand/
    profile.toml

settings.toml
  active_profile = "power_greatsword_virtuoso"
```

### 前端影响

- 增加 Profile selector。
- Settings / Skills / Points / Cycle Editor 都读取 active profile。
- 保存时保存当前 active profile。
- 可以提供“复制当前角色为新角色”。

### 后端影响

- `engine_start` 不再硬编码 `default`。
- `engine_preflight` 使用 active profile。
- Profile commands 增加读取/设置 active profile。
- 保持引擎仍然只运行当前 Profile 的第一个 rotation。

## Implementation Order

1. 写清两套 AHK 的状态机规格。
2. 增加多角色 Profile/active profile 能力。
3. 增加 observer/action slot，承载 `急速燃.a2`。
4. 手工创建两套角色配置：
   - `power_greatsword_virtuoso`
   - `condition_quickness_firebrand`
5. 根据实测施法条 ROI 调整各技能 start/complete detection。

## Risks

- AHK 中的 `SendLoop` 次数不能直接解释为施法时间，必须通过实测 ROI 校准。
- 屏幕像素坐标来自固定 UI 布局，分辨率或 UI 缩放变化会导致配置失效。
- `急速燃` 主循环里有重复块，迁移时需要抽象成 shared slot group，否则配置会膨胀。
- 多角色 Profile 会影响所有页面的数据加载路径，需要一次性收敛，避免某些页面仍读 `default`。

## Next Step

先实现多角色 Profile 与 active profile，再补 observer/action slot。完成后再进入两套手工配置。
