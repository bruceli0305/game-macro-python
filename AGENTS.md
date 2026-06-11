# AGENTS.md

## 1. 适用范围

本文件用于指导 AI 编码助手在本项目中的开发行为。

适用对象：
- GitHub Copilot / AI 编码助手
- 本地自动化编码代理
- 使用 AI 辅助开发、调试、重构的流程

本文件是开发约束，不是产品文档。

---

## 2. 项目背景

这是一个基于 Tauri 2 + Vue 3 + Rust 的桌面游戏宏辅助工具，聚焦《激战2》(Guild Wars 2)。

当前项目主线已经是 Tauri/Vue/Rust 实现。Python/PySide 不属于当前运行时、架构约束或新增开发目标；不要新增 Python 入口、恢复 Python 旧实现，或把 Python 方案作为当前功能的兼容路径。历史文档中出现的 Python 或迁移语境仅作为背景材料。

项目核心功能：
- 屏幕取色：标记关键像素点、读条区域和状态判定点。
- 技能管理：配置技能按键、施法时间、冷却时间和检测条件。
- 循环编排：可视化编辑技能循环序列，采用 Cycle Phase/Priority 调度模型，支持 AST 条件表达式。
- 宏执行：根据屏幕像素状态、运行时状态和循环配置发送按键，核心由 CycleExecutor 与 SkillAttemptExecutor 状态机承担。
- 离线推演：在前端模拟循环配置和运行时状态，辅助验证配置逻辑。

**必须遵守的道德和法律约束：**
- 不读游戏内存。
- 不注入游戏进程。
- 不实现外挂功能，如自动瞄准、透视、封包修改。
- 不绕过游戏客户端或服务端的安全机制。
- 不设计明显违反游戏服务条款的能力。
- 仅作为辅助工具，帮助玩家优化操作流程。

---

## 3. 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 桌面框架 | Tauri 2 | 跨平台桌面壳，Rust 后端 + Web 前端 |
| 前端 | Vue 3 + TypeScript + Vite | 响应式 UI，SFC 组件 |
| 状态管理 | Pinia | Vue 3 官方状态管理 |
| UI 组件库 | Naive UI | TypeScript 优先，暗色模式内置 |
| CSS | Tailwind CSS v4 | 原子化 CSS，与 Naive UI 共存 |
| 图标 | @tabler/icons-vue | 桌面工具风格图标 |
| 后端 | Rust edition 2024 | 性能关键路径：引擎、截屏、发键 |
| 异步运行时 | tokio + tokio-util | Tauri 2 内部运行时，引擎任务和取消信号复用 |
| 序列化 | serde + serde_json | Rust 模型、JSON、TypeScript 类型对齐 |
| 持久化 | TOML 文件 | 配置文件格式，人类可读 |
| 截屏 | xcap | 跨平台屏幕捕获 |
| 图像处理 | image | 像素采样、颜色比较、ROI 检测 |
| 发键 | enigo | 跨平台键盘模拟 |
| 全局热键 | tauri-plugin-global-shortcut | 取色确认、引擎启停热键 |
| 文件对话框 | tauri-plugin-dialog | 导入、导出、选择配置文件 |
| Shell 插件 | tauri-plugin-shell | 受控调用系统能力 |
| 日志 | tracing + tracing-subscriber | 结构化日志和过滤 |
| Rust 测试 | cargo test + tempfile | 单元测试、临时目录和持久化测试 |
| 前端测试 | vitest + @vue/test-utils | 逻辑、store、组件测试 |
| 代码编辑器 | CodeMirror 6 | JSON/AST 表达式编辑 |
| 拖拽排序 | vue-draggable-plus | SortableJS 的 Vue 3 封装 |
| 工具函数 | @vueuse/core | useStorage, useThrottleFn, useEventListener 等 |

---

## 4. 架构约束

必须遵守以下分层架构：

```text
src-tauri/                       <- Rust 后端（Tauri）
├── src/
│   ├── main.rs                  <- Tauri 入口
│   ├── lib.rs                   <- 库根与应用装配
│   ├── commands/                <- Tauri IPC 命令薄层
│   │   ├── engine_cmd.rs        <- 引擎启停、暂停、步进、运行时状态
│   │   ├── capture_cmd.rs       <- 取色会话、屏幕采样
│   │   ├── profile_cmd.rs       <- 配置 CRUD
│   │   └── skill_cmd.rs         <- 技能数据查询
│   ├── engine/                  <- 宏执行引擎，不依赖 Tauri commands
│   │   ├── cycle_executor.rs    <- Phase/Priority 调度循环
│   │   ├── skill_attempt.rs     <- 技能尝试状态机
│   │   ├── attempt_tracker.rs   <- 尝试事件与追踪
│   │   ├── phase_manager.rs     <- 阶段切换与阶段状态
│   │   ├── runtime_config.rs    <- 运行时配置编译
│   │   ├── runtime_state.rs     <- 运行时聚合指标
│   │   └── scheduler.rs         <- 调度器
│   ├── ast/                     <- 条件表达式 AST，纯逻辑
│   │   ├── nodes.rs             <- Expr 枚举
│   │   ├── evaluator.rs         <- 三值逻辑求值器
│   │   ├── compiler.rs          <- JSON 到 Expr 编译、校验、探针收集
│   │   └── codec.rs             <- Serde 序列化、反序列化
│   ├── capture/                 <- 屏幕截取和像素检测
│   │   ├── capturer.rs          <- xcap 封装
│   │   ├── cast_bar_roi.rs      <- 读条区域检测
│   │   └── mod.rs               <- Capture 模块声明
│   ├── input/                   <- 模拟按键
│   │   └── key_sender.rs        <- enigo 封装
│   ├── models/                  <- 数据模型，Serde derive，不放业务逻辑
│   ├── store/                   <- TOML 持久化
│   └── error.rs                 <- 统一错误类型
├── assets/gw2/                  <- 历史仓库级 GW2 数据目录；当前不作为运行路径
├── icons/                       <- 应用图标
├── Cargo.toml
└── tauri.conf.json

src/                             <- Vue 3 前端
├── App.vue
├── main.ts
├── style.css
├── router/                      <- 路由
├── stores/                      <- Pinia 状态
├── views/                       <- 页面
├── components/                  <- UI 组件
│   ├── common/
│   ├── editor/
│   ├── engine/
│   └── picker/
├── composables/                 <- IPC、热键、业务流程封装
├── types/                       <- 与 Rust models 对齐的 TypeScript 类型
├── utils/                       <- 前端纯函数、校验、模板、模拟工具
├── assets/json/                 <- 前端预设和种子数据
└── __tests__/                   <- 前端测试
```

**模块边界规则：**
- `src-tauri/src/ast/` 不得依赖 Tauri、tokio 或任何 I/O，只做纯 CPU 计算。
- `src-tauri/src/models/` 只包含数据结构、Serde derive 和必要的类型定义，不包含业务流程。
- `src-tauri/src/store/` 只负责文件读写、路径处理和序列化，不放引擎或 UI 逻辑。
- `src-tauri/src/engine/` 可以依赖 `ast/`、`capture/`、`input/`、`models/`，不依赖 `commands/`。
- `src-tauri/src/commands/` 是 IPC 薄层，只做参数校验、状态提取、调用后端模块和结果转换。
- 前端 `views/` 不直接调用 Tauri `invoke()` 或 `listen()`，必须通过 `composables/` 封装。
- 前端 `stores/` 持有跨组件状态；组件可以通过 store action 修改状态，避免在页面里散落业务状态迁移。
- 前端 `types/` 必须与 Rust `models/` 字段对齐。任一侧模型变更都要同步另一侧。
- `utils/` 只能放可测试的纯逻辑或轻量适配，不能偷偷承载 IPC 或全局副作用。

---

## 5. Rust 代码风格

### 5.1 通用规则

- 遵循 `cargo fmt` 和 `cargo clippy`。
- 公共类型、公共函数和跨模块行为要有清晰 `///` 文档注释。
- 错误类型使用 `thiserror::Error` derive，不用裸 `String` 表示可恢复错误。
- 库代码避免 `unwrap()` / `expect()`，优先使用 `?` 和项目统一错误类型。
- 日志使用 `tracing`，不要使用 `println!` 留在正式路径。
- 不把 Tauri 类型泄漏到 engine、ast、capture plan、models 等核心模块。

### 5.2 命名约定

- 类型、枚举、Trait：`PascalCase`。
- 函数、方法、变量：`snake_case`。
- 常量、静态：`SCREAMING_SNAKE_CASE`。
- 模块文件：`snake_case.rs`。
- 私有成员不加特殊前缀，用 `pub` / `pub(crate)` 控制可见性。

### 5.3 模块组织

- 每个 `mod.rs` 负责声明子模块，并用 `pub use` 重导出稳定公开类型。
- 避免深层嵌套，优先通过小模块和清晰类型表达边界。
- `use` 语句按 std、第三方、crate、super 分组。
- 共享模型优先放 `models/`；运行期派生状态优先放 `engine/runtime_state.rs` 或更贴近的 engine 子模块。

### 5.4 异步代码

- 引擎主循环用 `tokio::spawn` 在独立 task 中运行。
- 停止信号使用 `tokio_util::sync::CancellationToken`。
- 避免用无界 `tokio::time::sleep` 做粗暴轮询；需要等待状态变化时优先考虑 `Notify`、`watch`、`mpsc` 或明确的 tick 策略。
- Tauri command 使用 `async` + `State<'_, AppState>`，不要在 command 中实现复杂业务状态机。

---

## 6. Vue 3 / TypeScript 代码风格

### 6.1 通用规则

- 使用 `<script setup lang="ts">`。
- 组件文件和模板组件名使用 `PascalCase`。
- 组合式函数用 `useXxx` 命名，封装 IPC、订阅、浏览器事件或复用流程。
- 类型定义放在 `src/types/`，优先使用 `interface` 或清晰的联合类型。
- 前端业务校验放在 `src/utils/` 并配套测试，不要散落在多个组件里。

### 6.2 命名约定

- 组件文件：`PascalCase.vue`。
- 组合式函数：`usePascalCase.ts`。
- Store 文件：`kebab-case.ts` 或已有 store 命名风格。
- 类型文件：`kebab-case.ts`。

### 6.3 组件通信

- 父到子：`defineProps<{ ... }>()`。
- 子到父：`defineEmits<{ ... }>()`。
- 跨组件状态：Pinia store。
- Tauri 事件订阅：通过 composable 封装 `listen()`，负责取消订阅和生命周期清理。
- 页面组件只编排布局和流程，不直接实现底层 IPC 细节。

### 6.4 性能与交互

- 大列表优先使用 Naive UI virtual-list 或等价虚拟化方案。
- 深层 AST、配置树、运行时快照等对象使用 `shallowRef` 或明确的不可变更新策略，避免无意义深层响应式开销。
- 高频取色、鼠标位置、运行时指标刷新使用节流或 animation frame 策略。
- UI 修改必须考虑桌面窗口尺寸，避免文本溢出、按钮跳动和状态面板互相遮挡。

---

## 7. 开发行为要求

### 7.1 开始开发前

开始编码前，先完成：
- 阅读相关模块的代码和已有文档。
- 明确当前任务影响范围。
- 确认改动是否符合模块边界。
- 列出最小改动面。

### 7.2 开发过程中

开发时必须：
- 保持模块边界清晰。
- 优先修根因，不在 UI 层掩盖后端模型或状态机问题。
- 使用 TypeScript 严格模式和 Rust 编译、测试工具验证改动。
- 避免把调试代码、临时日志、临时按钮留在正式路径。
- 避免过度抽象。只有当抽象能减少真实重复、收束边界或匹配现有模式时才新增。

### 7.3 开发完成后

按改动范围执行验证：
- Rust 改动：在 `src-tauri/` 运行 `cargo test`，并尽量运行 `cargo clippy -- -D warnings`。
- 前端类型或组件改动：运行 `pnpm exec vue-tsc --noEmit`。
- 前端逻辑或组件改动：运行 `pnpm test`，必要时只跑相关 vitest 用例后说明范围。
- 跨 IPC、配置、运行时流程改动：同时做 Rust 与前端验证，并检查关键日志字段。
- 仅文档改动：至少检查关键词、路径和编码，不需要跑全量测试。

无法执行某类验证时，必须在最终输出说明原因和残留风险。

---

## 8. 代码修改规则

### 8.1 优先修根因

如果问题来自数据模型，就改模型并同步 TypeScript 类型。
如果问题来自状态机，就修正状态迁移和对应测试。
如果问题来自模块边界混乱，就收敛边界。
不要只在调用方加判断掩盖问题。

### 8.2 改动必须最小且集中

一次改动只解决一个明确问题或一组强相关问题。不要顺手扩散重构、格式化无关文件或修改无关配置。

### 8.3 变更必须可追踪

任何以下变更，都要同步写入文档、类型或注释：
- Rust struct / enum 字段变化，以及对应 TypeScript 类型变化。
- 配置文件结构、默认值或持久化路径变化。
- 错误类型、错误码或 IPC 返回结构变化。
- 日志字段、事件名或运行时指标变化。
- 任务流、调度模型、状态机迁移规则变化。
- `#[tauri::command]` 的名称、参数或返回值变化。

---

## 9. 测试与验证规则

### 9.1 每次改动至少做一类验证

至少完成以下之一：
- Rust 单元测试或集成测试。
- Vue / TypeScript 单元测试。
- 类型检查。
- 手动集成测试。
- 针对文档和配置的关键词、路径、编码检查。

### 9.2 修 bug 必须补回归

修 bug 时必须新增对应测试或最小复现实例。确实不适合自动化时，要记录手动验证步骤。

### 9.3 无验证不允许宣称完成

没有验证结果时，不要输出“已修复”或“已完成”。只能说明已修改，并明确未验证的风险。

### 9.4 必须重点覆盖的模块

以下模块必须保持单元测试覆盖，目标高于普通 UI 代码：
- `src-tauri/src/ast/evaluator.rs`：三值逻辑求值器。
- `src-tauri/src/ast/compiler.rs`：JSON 到 Expr 编译、语义错误检测、探针收集。
- `src-tauri/src/engine/cycle_executor.rs`：Phase/Priority 调度正确性。
- `src-tauri/src/engine/skill_attempt.rs`：技能尝试状态机转移。
- `src-tauri/src/engine/phase_manager.rs`：阶段切换规则。
- `src-tauri/src/capture/cast_bar_roi.rs`：读条 ROI 检测和采样统计。
- `src/utils/profile-validation.ts`、`src/utils/runtime-actions.ts` 等前端纯业务逻辑。

---

## 10. 日志规则

Rust 侧使用 `tracing`：
- `info!`：引擎启动、停止、配置加载、配置保存。
- `debug!`：单个技能执行、条件求值、截屏采样、调度决策。
- `warn!`：可恢复失败、重试、截屏失败回退、锁等待超时。
- `error!`：引擎任务崩溃、发键失败、配置损坏、不可恢复 IPC 错误。

关键流程必须尽量记录开始、完成、失败三个阶段，并在复杂流程使用 span 关联上下文。

前端侧通过 Tauri 事件接收引擎日志，并在 ExecLogViewer 或等价组件中展示。不要只在浏览器 console 中输出关键运行信息。

---

## 11. 禁止项总结

以下行为明确禁止：
- 新增、恢复或依赖 Python/PySide 运行路径。
- 读取游戏内存或注入游戏进程。
- 实现明显违反游戏服务条款的功能。
- 打补丁掩盖根因。
- 无测试或无验证就宣称修复。
- 用 UI 层偷偷兜底后端模型、调度或状态机问题。
- 前端直接调用 Tauri `invoke()` 或 `listen()`，绕过 composables。
- 在 Rust 库代码中使用 `unwrap()` / `expect()` 处理可恢复错误。
- 混用互不兼容的数据协议、事件名或配置格式。
- 提交无关格式化、无关重构或临时调试代码。

---

## 12. 建议执行节奏

建议 AI 助手在每次任务中遵守以下节奏：
1. 先读相关文档和代码。
2. 再判断根因或实现入口。
3. 再做最小充分改动。
4. 再补日志、类型和测试。
5. 最后更新相关文档并说明验证结果。

---

## 13. 文件组织

### 13.1 资源文件

- `src-tauri/assets/gw2/`：Tauri 后端打包和运行使用的 GW2 数据文件，是当前唯一运行时 GW2 数据路径。
- `src/assets/json/`：前端预设、模板和种子数据。
- `src-tauri/icons/`：应用图标。

### 13.2 配置文件

- `src-tauri/Cargo.toml`：Rust 依赖和构建配置。
- `package.json`：Node.js 依赖和前端脚本。
- `pnpm-lock.yaml`：前端依赖锁定。
- `tsconfig.json`：TypeScript 配置。
- `vite.config.ts`：Vite 配置。
- `src-tauri/tauri.conf.json`：Tauri 配置。
- `.gitignore`：Git 忽略规则。

### 13.3 测试文件

- `src-tauri/src/` 内各模块的 `#[cfg(test)] mod tests`：Rust 单元测试。
- `src/__tests__/`：前端单元和组件测试。

---

## 14. 进度文档规则

较大开发任务结束后，建议在 `docs/` 输出一份进度文档，至少包括：

```md
# Progress

## Goal
## Done
## Files Changed
## Root Cause / Key Decision
## Logs / Tests
## Risks
## Next Step
```

文件命名建议：

```text
YYYY-MM-DD_<task-id>_<short-name>.md
```

小型文档修正、拼写修正或无行为变化的清理可以只在最终回复中说明，不强制新增进度文档。

---

## 15. 输出风格要求

当 AI 助手输出研发结论时，应优先使用以下结构：
1. 目标
2. 根因或设计判断
3. 改动方案
4. 实际改动文件
5. 测试与日志
6. 风险与下一步

不要只给出代码片段而不说明影响范围。

---

## 附录 A：Rust 依赖速查

| Crate | 版本 | 用途 | 选型理由 |
|---|---|---|---|
| `tauri` | 2.x | 桌面框架 | 跨平台，Rust 后端 + Web 前端 |
| `tauri-plugin-global-shortcut` | 2.x | 全局热键 | Tauri 官方插件 |
| `tauri-plugin-dialog` | 2.x | 文件对话框 | 导入、导出配置 |
| `tauri-plugin-shell` | 2.x | Shell 能力 | 受控调用系统能力 |
| `xcap` | 0.9 | 屏幕截取 | 跨平台屏幕捕获 |
| `image` | 0.25 | 图像处理 | 像素采样和颜色比较 |
| `enigo` | 0.6 | 发键 | 跨平台输入模拟 |
| `serde` | 1.x | 序列化 | Rust 标准 derive |
| `serde_json` | 1.x | JSON | 与前端通信格式一致 |
| `toml` | 0.8 | TOML 配置 | 人类可读配置格式 |
| `tokio` | 1.x | 异步运行时 | 引擎 task 与 Tauri 运行时协作 |
| `tokio-util` | 0.7 | 异步工具 | CancellationToken |
| `tracing` | 0.1 | 结构化日志 | 适合异步上下文 |
| `tracing-subscriber` | 0.3 | 日志订阅 | 过滤和输出配置 |
| `thiserror` | 2.x | 错误类型 derive | 减少错误样板代码 |
| `uuid` | 1.x | ID 生成 | v4 随机 UUID |
| `tempfile` | 3.x | 测试临时文件 | 持久化和文件系统测试 |

### 备选/待评估

| Crate | 场景 | 备注 |
|---|---|---|
| `windows` crate | Win32 API 直调 | 如果 enigo 在目标场景发键失效，再评估 `SendInput` |
| `rusqlite` | SQLite 存储 | 配置规模或查询复杂度上升后再评估 |
| `scrap` | 截屏备选 | 仅在 xcap 无法满足平台需求时评估 |

---

## 附录 B：Node.js / Vue 3 依赖速查

| 包 | 版本 | 用途 | 选型理由 |
|---|---|---|---|
| `vue` | ^3.5 | 前端框架 | Composition API + `<script setup>` |
| `vite` | ^6 | 构建工具 | Tauri 推荐，HMR 快 |
| `typescript` | ^5 | 类型系统 | 与 Rust 模型对齐 |
| `vue-router` | ^4 | 路由 | SPA 页面切换 |
| `pinia` | ^2 | 状态管理 | Vue 3 官方状态管理 |
| `naive-ui` | ^2 | UI 组件库 | TypeScript 友好，暗色内置 |
| `tailwindcss` | ^4 | CSS 框架 | 原子化样式 |
| `@tailwindcss/vite` | ^4 | Tailwind Vite 插件 | Tailwind v4 集成 |
| `@tabler/icons-vue` | ^3 | 图标 | 桌面工具图标 |
| `@tauri-apps/api` | ^2 | Tauri IPC | 前端 invoke/listen API |
| `@tauri-apps/plugin-global-shortcut` | ^2 | 全局热键 | Tauri 官方插件 |
| `@tauri-apps/plugin-dialog` | ^2 | 文件对话框 | Tauri 官方插件 |
| `vue-draggable-plus` | ^0.5 | 拖拽排序 | SortableJS 的 Vue 3 封装 |
| `@vueuse/core` | ^12 | 组合式工具 | 常用响应式工具 |
| `codemirror` | ^6 | 代码编辑器 | JSON/AST 表达式编辑 |
| `@codemirror/lang-json` | ^6 | JSON 语法 | CodeMirror JSON 高亮 |
| `@codemirror/view` | ^6 | 编辑器视图 | CodeMirror 视图层 |
| `@codemirror/state` | ^6 | 编辑器状态 | CodeMirror 状态层 |
| `vitest` | ^3 | 测试框架 | Vite 原生测试 |
| `@vue/test-utils` | ^2 | 组件测试 | Vue 3 官方测试工具 |
| `vue-tsc` | ^2 | 类型检查 | 支持 `.vue` 文件 |
| `@tauri-apps/cli` | ^2 | Tauri CLI | 构建和开发命令 |
| `eslint` | ^9 | 代码检查 | 前端 lint |
| `@vue/eslint-config-typescript` | ^14 | ESLint TS 配置 | Vue + TS lint 支持 |
| `prettier` | ^3 | 格式化 | 统一前端格式 |

### 备选/待评估

| 包 | 场景 | 备注 |
|---|---|---|
| `PrimeVue` | 备选 UI 库 | 组件更多但更重 |
| `Element Plus` | 备选 UI 库 | 成熟但偏 Web 应用风格 |
| `@guolao/vue-monaco-editor` | 备选编辑器 | 功能强但体积更大 |
| `lucide-vue-next` | 备选图标 | 更简洁，图标数量少于 Tabler |
| `UnoCSS` | 备选 CSS | 仅在 Tailwind v4 不满足需求时评估 |
