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

这是一个桌面游戏宏工具项目，聚焦《激战2》(Guild Wars 2)。
**当前为 v2 重构版：技术栈从 Python/PySide6 迁移到 Tauri 2 + Vue 3 + Rust。**

项目核心功能：
- 屏幕取色：标记关键像素点（如技能冷却指示灯）
- 技能管理：配置技能按键、施法时间、冷却时间
- 循环编排：可视化编辑技能循环序列（Cycle Phase/Priority 调度模型，支持 AST 条件表达式）
- 宏执行：根据屏幕像素状态自动发送按键（CycleExecutor + SkillAttemptExecutor 状态机）

**必须遵守的道德和法律约束：**
- 不读游戏内存
- 不注入游戏进程
- 不实现外挂功能（如自动瞄准、透视）
- 不违反游戏服务条款
- 仅作为辅助工具，帮助玩家优化操作流程

---

## 3. 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 桌面框架 | Tauri 2 | 跨平台桌面壳，Rust 后端 + Web 前端 |
| 前端 | Vue 3 + TypeScript + Vite | 响应式 UI，SFC 组件 |
| 状态管理 | Pinia | Vue 3 官方状态管理 |
| UI 组件库 | Naive UI | TypeScript 优先，tree-shaking，暗色模式内置 |
| CSS | Tailwind CSS v4 | 原子化 CSS |
| 图标 | @tabler/icons-vue | 4000+ MIT 图标 |
| 后端 | Rust (edition 2024) | 性能关键路径：引擎、截屏、发键 |
| 异步运行时 | tokio | Tauri 2 内部使用，引擎也用 tokio task |
| 序列化 | serde + serde_json | Rust 模型 ↔ JSON ↔ TypeScript |
| 截屏 | xcap | 跨平台屏幕捕获（X11/Wayland/macOS/Windows） |
| 图像处理 | image | 像素采样、颜色操作 |
| 发键 | enigo | 跨平台键盘/鼠标模拟 |
| 全局热键 | Tauri global-shortcut 插件 | 取色确认、引擎启停热键 |
| 持久化 | TOML 文件（serde） | 配置文件格式，人类可读（后续可迁 SQLite） |
| 日志 | tracing | 结构化异步日志 |
| 测试(Rust) | tokio-test + rstest | 异步测试 + 固件 |
| 测试(前端) | vitest + @vue/test-utils | 组件测试 |
| 代码编辑器 | CodeMirror 6 | 轻量级 JSON/AST 表达式编辑 |
| 拖拽排序 | vue-draggable-plus | SortableJS 的 Vue 3 封装 |
| 工具函数 | @vueuse/core | useStorage, useThrottleFn, useEventListener 等 |

---

## 4. 架构约束

必须遵守以下分层架构：

```
src-tauri/                       ← Rust 后端（Tauri）
├── src/
│   ├── main.rs                  ← Tauri 入口
│   ├── lib.rs                   ← 库根
│   ├── commands/                ← Tauri IPC 命令（薄层，转发到 services）
│   │   ├── mod.rs
│   │   ├── engine_cmd.rs        ← 引擎启停/暂停/步进
│   │   ├── capture_cmd.rs       ← 取色会话
│   │   ├── profile_cmd.rs       ← 配置 CRUD
│   │   └── skill_cmd.rs         ← 技能管理
│   ├── engine/                  ← 宏执行引擎（不依赖 Tauri）
│   │   ├── mod.rs
│   │   ├── cycle_executor.rs    ← Phase/Priority 调度循环
│   │   ├── skill_attempt.rs     ← 技能尝试状态机
│   │   ├── scheduler.rs         ← 调度器
│   │   └── runtime_state.rs     ← 运行时聚合指标 + MetricProvider
│   ├── ast/                     ← 条件表达式 AST（纯逻辑，零依赖）
│   │   ├── mod.rs
│   │   ├── nodes.rs             ← Expr 枚举（And/Or/Not/PixelMatch/…）
│   │   ├── evaluator.rs         ← 三值逻辑求值器（TriBool）
│   │   ├── compiler.rs          ← JSON → Expr 编译 + 语义校验 + 探针收集
│   │   └── codec.rs             ← Serde 序列化/反序列化
│   ├── capture/                 ← 屏幕截取
│   │   ├── mod.rs
│   │   ├── capturer.rs          ← xcap 封装 + 快照缓存 + 退避
│   │   ├── scanner.rs           ← 像素采样 + CapturePlan 执行
│   │   └── plan.rs              ← CapturePlan ↔ ProbeRequirements
│   ├── input/                   ← 模拟按键
│   │   ├── mod.rs
│   │   └── key_sender.rs        ← enigo 封装
│   ├── models/                  ← 数据模型（Serde derive，不含业务逻辑）
│   │   ├── mod.rs
│   │   ├── skill.rs
│   │   ├── point.rs
│   │   ├── base.rs
│   │   ├── cycle.rs
│   │   └── profile.rs
│   ├── store/                   ← 持久化层
│   │   ├── mod.rs
│   │   └── profile_store.rs     ← TOML 文件读写
│   └── error.rs                 ← 统一错误类型（thiserror）
├── Cargo.toml
└── tauri.conf.json

src/                             ← Vue 3 前端
├── App.vue
├── main.ts
├── router/
│   └── index.ts
├── stores/                      ← Pinia 状态管理
│   ├── profile.ts               ← 当前 Profile 状态 + 脏标记
│   ├── engine.ts                ← 引擎运行时状态（实时指标订阅）
│   └── picker.ts                ← 取色会话状态
├── views/                       ← 页面（对应路由）
│   ├── SettingsPage.vue         ← 基础配置
│   ├── SkillsPage.vue           ← 技能管理
│   ├── PointsPage.vue           ← 点位管理
│   ├── CycleEditorPage.vue      ← 阶段循环编辑器（核心）
│   └── SimulatorPage.vue        ← 离线推演
├── components/                  ← 通用组件
│   ├── editor/                  ← 循环编辑器子组件
│   │   ├── PhaseList.vue
│   │   ├── SkillSlotCard.vue
│   │   ├── ConditionBuilder.vue ← AST 条件可视化构建
│   │   └── TimelinePreview.vue
│   ├── picker/                  ← 取色相关
│   │   └── PixelPreview.vue
│   ├── common/
│   │   ├── ColorSwatch.vue
│   │   ├── HotkeyInput.vue
│   │   └── SkillSelector.vue
│   └── engine/
│       ├── EngineControlBar.vue ← 启停/暂停/步进
│       ├── SkillStatusGrid.vue  ← 实时技能状态表格
│       └── ExecLogViewer.vue    ← 执行日志流
├── composables/                 ← 组合式函数
│   ├── useEngine.ts             ← 引擎 IPC 封装
│   ├── useCapture.ts            ← 取色 IPC 封装
│   └── useProfile.ts            ← 配置 IPC 封装
└── types/                       ← TypeScript 类型（与 Rust models/ 对齐）
    ├── skill.ts
    ├── cycle.ts
    ├── engine.ts
    └── ast.ts
```

**模块边界规则：**
- `src-tauri/src/ast/` 不得依赖 Tauri、tokio 或任何 I/O，只做纯 CPU 计算
- `src-tauri/src/engine/` 依赖 `ast/`、`capture/`、`input/`，不依赖 Tauri commands
- `src-tauri/src/commands/` 是薄层，只做参数校验 + 调用 engine/service + 返回结果
- `src-tauri/src/models/` 只包含 `#[derive(Serialize, Deserialize)]` 的 struct/enum，不包含业务逻辑
- `src-tauri/src/store/` 只负责文件读写，不包含业务逻辑
- 前端 `views/` 不直接调用 Tauri `invoke()`，通过 `composables/` 封装
- 前端 `stores/` 持有所有状态，组件只读不直接写
- 前端 `types/` 必须与 Rust `models/` 字段对齐

---

## 5. Rust 代码风格

### 5.1 通用规则
- 遵循 `cargo fmt` 和 `cargo clippy`（`clippy::pedantic`）
- 使用 `rustfmt.toml` 统一格式
- 所有 `pub` 类型必须有 `///` 文档注释
- 错误类型使用 `thiserror::Error` derive，不用裸 `String`
- 避免 `unwrap()` / `expect()` 在库代码中，使用 `?` 和 `Result`

### 5.2 命名约定
- 类型/枚举/Trait：`PascalCase`（Rust 默认）
- 函数/方法/变量：`snake_case`（Rust 默认）
- 常量/静态：`SCREAMING_SNAKE_CASE`
- 模块文件：`snake_case.rs`
- 私有成员：无特殊前缀（Rust 用 `pub`/`pub(crate)` 控制可见性）

### 5.3 模块组织
- 每个 `mod.rs` 用 `pub use` 重导出公开类型
- 避免深层嵌套（最多 3 层）
- `use` 语句按：std → 第三方 → crate → super 分组

### 5.4 异步代码
- 引擎主循环用 `tokio::spawn` 在独立 task 中运行
- 停止信号用 `tokio::sync::CancellationToken`
- 避免 `tokio::time::sleep` 做轮询，优先用 `tokio::sync::Notify` / `watch` channel
- Tauri command 中用 `async` + `State<'_, AppState>`

---

## 6. Vue 3 / TypeScript 代码风格

### 6.1 通用规则
- 使用 `<script setup lang="ts">` 语法
- 组件名用 `PascalCase`（文件名和模板中都用 PascalCase）
- 组合式函数用 `useXxx` 命名，返回 `{ ref, computed, method }`
- 类型定义放在 `types/` 目录，用 `interface` 或 `type`

### 6.2 命名约定
- 组件文件：`PascalCase.vue`
- 组合式函数：`usePascalCase.ts`
- Store 文件：`kebab-case.ts`
- 类型文件：`kebab-case.ts`

### 6.3 组件通信
- 父→子：`defineProps<{ ... }>()`（TypeScript 泛型）
- 子→父：`defineEmits<{ ... }>()`
- 跨组件状态：Pinia store（不用 provide/inject 做复杂状态）
- 事件总线：用 composable 封装 Tauri `listen()` 事件订阅

### 6.4 性能
- 大列表用 Naive UI 的 virtual-list
- 条件构建器用 `shallowRef` 包裹深度 AST 对象
- 取色预览用 `requestAnimationFrame` 节流

---

## 7. 开发行为要求

### 7.1 开始开发前

开始编码前，先完成：
- 阅读相关模块的代码和文档
- 明确当前任务的影响范围
- 确认改动是否符合架构约束
- 列出最小改动面

### 7.2 开发过程中

开发时必须：
- 保持模块边界清晰
- 避免跨层越权调用
- 使用 TypeScript 严格模式（前端）和 `cargo clippy`（后端）
- 避免把调试代码留在正式路径
- 避免过度抽象

### 7.3 开发完成后

必须完成：
- Rust 侧：`cargo test` + `cargo clippy` 无新增 warning
- 前端侧：`vue-tsc --noEmit` + `vitest run`
- 检查关键日志（tracing）
- 更新相关文档
- 记录遗留问题

---

## 8. 代码修改规则

### 8.1 优先修根因，不做表面修饰

如果问题来自数据模型错误，就改模型。
如果问题来自状态迁移错误，就改状态机。
如果问题来自模块边界混乱，就收敛边界。
不要只在调用方加判断掩盖问题。

### 8.2 改动必须最小且集中

一次改动只解决一个明确问题或一组强相关问题，不要顺手扩散重构。

### 8.3 变更必须可追踪

任何以下变更，都要同步写入文档或注释：
- 数据模型变化（Rust struct 字段变更 + TypeScript 类型同步）
- 配置项变化
- 错误码变化
- 日志字段变化
- 任务流变化
- IPC 命令签名变化（`#[tauri::command]` 参数变化）

---

## 9. 测试与验证规则

### 9.1 每次改动至少做一类验证

至少完成以下之一：
- Rust 单元测试（`#[cfg(test)] mod tests`）
- Vue 组件测试（`vitest` + `@vue/test-utils`）
- 手动集成测试
- 最小复现实例

### 9.2 修 bug 必须补回归

修 bug 时必须新增对应测试或用例。

### 9.3 无验证不允许宣称完成

没有验证结果时，不要输出"已修复""已完成"。

### 9.4 必须测试的模块

以下模块必须有单元测试覆盖（目标 >80%）：
- `ast/evaluator.rs` — 三值逻辑求值器（Kleene 逻辑正确性）
- `ast/compiler.rs` — JSON → Expr 编译 + 语义错误检测
- `engine/cycle_executor.rs` — Phase/Priority 调度正确性
- `engine/skill_attempt.rs` — 状态机转移正确性
- `capture/plan.rs` — Plan 构建 + 探针去重

---

## 10. 日志规则

Rust 侧使用 `tracing` crate：
- `info!`：引擎启动/停止，配置加载/保存
- `debug!`：单个技能执行，条件求值，截屏事件
- `warn!`：重试、截屏失败回退、锁等待超时
- `error!`：引擎崩溃、发键失败、配置损坏

关键流程必须记录开始、完成、失败三个阶段（span）。

前端侧通过 Tauri 事件接收引擎日志，在 ExecLogViewer 中展示。

---

## 11. 禁止项总结

以下行为明确禁止：
- 打补丁掩盖问题
- 为旧实现做兼容
- 不找根因直接改代码
- 无日志关键路径
- 无测试就宣称修复
- 混用旧协议和新协议
- 用 UI 层偷偷兜底业务问题
- 违反游戏服务条款的功能
- 读取游戏内存或注入进程
- 前端直接调用 Tauri `invoke()`（必须通过 composables 封装）
- Rust `unwrap()` 在库代码中（应返回 `Result`）

---

## 12. 建议执行习惯

建议 AI 助手在每次任务中遵守以下节奏：
1. 先读文档和相关代码
2. 再判断问题根因或实现入口
3. 再做最小充分改动
4. 再补日志和测试
5. 最后更新相关文档

这比"先改了再说"更符合本项目要求。

---

## 13. 文件组织

### 13.1 资源文件
- `assets/icons/`：应用图标
- `assets/json/gw2/`：Guild Wars 2 API 数据文件（技能/专精等）

### 13.2 配置文件
- `src-tauri/Cargo.toml`：Rust 依赖
- `package.json`：Node.js 依赖
- `.gitignore`：Git 忽略规则
- `LICENSE`：MIT 许可证
- `rustfmt.toml`：Rust 格式化配置
- `src-tauri/tauri.conf.json`：Tauri 配置

### 13.3 测试文件
- `src-tauri/src/` 内各模块的 `#[cfg(test)] mod tests`：Rust 单元测试
- `src/__tests__/`：前端单元/组件测试

---

## 14. 进度文档规则

每次开发结束后，建议输出一份进度文档，至少包括：

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
| `tauri-plugin-global-shortcut` | 2.x | 全局热键 | Tauri 官方插件，比 rdev 集成更顺畅 |
| `tauri-plugin-dialog` | 2.x | 文件对话框 | 导入/导出配置 |
| `xcap` | 0.9 | 屏幕截取 | 跨平台（X11/Wayland/macOS/Windows），API 清晰，活跃维护（971 ★） |
| `image` | 0.25 | 图像处理 | xcap 的依赖，直接复用做像素采样 |
| `enigo` | 0.x | 发键/鼠标模拟 | 跨平台输入模拟，成熟稳定 |
| `serde` | 1.x | 序列化 | Rust 标准，derive 宏 |
| `serde_json` | 1.x | JSON | 与前端通信格式一致 |
| `toml` | 0.8 | TOML 配置 | 比 JSON 更适合配置文件，人类可读 |
| `tokio` | 1.x | 异步运行时 | Tauri 2 内部使用，引擎复用同一运行时 |
| `tracing` | 0.1 | 结构化日志 | 比 `log` 更适合异步上下文，Tauri 集成 |
| `tracing-subscriber` | 0.3 | 日志订阅 | 配置日志输出格式/级别 |
| `thiserror` | 2.x | 错误类型 derive | 减少 boilerplate |
| `uuid` | 1.x | ID 生成 | 替代自建 Snowflake，用 v4 随机 UUID |
| `tokio-test` | 0.4 | 异步测试 | 模拟 tokio 运行时 |
| `rstest` | 0.x | 固件测试 | 类似 pytest fixtures |

### 备选/待评估

| Crate | 场景 | 备注 |
|---|---|---|
| `rdev` | 全局热键（备选） | listen + simulate + grab，但 Wayland 不支持。Tauri 官方插件优先 |
| `rusqlite` | SQLite 存储 | 后期迁移用，初期 TOML 文件即可 |
| `windows` crate | Win32 API 直调 | 如果 enigo 在游戏窗口发键失效，用 `SendInput` 替代 |
| `scrap` | 截屏（备选） | xcap 的备选，但维护不如 xcap 活跃 |

---

## 附录 B：Node.js / Vue 3 依赖速查

| 包 | 版本 | 用途 | 选型理由 |
|---|---|---|---|
| `vue` | ^3.5 | 前端框架 | Composition API + `<script setup>` |
| `vite` | ^6 | 构建工具 | Tauri 推荐，HMR 极快 |
| `typescript` | ^5 | 类型系统 | 严格模式，与 Rust 模型对齐 |
| `vue-router` | ^4 | 路由 | SPA 页面切换 |
| `pinia` | ^2 | 状态管理 | Vue 3 官方，DevTools 支持 |
| `naive-ui` | ^2 | UI 组件库 | TypeScript 优先，tree-shaking，暗色内置，桌面感好 |
| `tailwindcss` | ^4 | CSS 框架 | 原子化，与 Naive UI 共存 |
| `@tabler/icons-vue` | ^3 | 图标 | 4000+ MIT 图标，桌面风格 |
| `@tauri-apps/api` | ^2 | Tauri IPC | 前端 invoke/listen |
| `@tauri-apps/plugin-global-shortcut` | ^2 | 全局热键 | Tauri 官方 |
| `@tauri-apps/plugin-dialog` | ^2 | 文件对话框 | Tauri 官方 |
| `vue-draggable-plus` | ^0.x | 拖拽排序 | SortableJS 的 Vue 3 封装，PhaseList 排序用 |
| `@vueuse/core` | ^12 | 组合式工具 | useStorage, useThrottleFn, useEventListener 等 |
| `codemirror` | ^6 | 代码编辑器 | 轻量（~500KB），JSON/AST 表达式编辑用 |
| `@codemirror/lang-json` | ^6 | JSON 语法 | CodeMirror 6 的 JSON 语法高亮 |
| `@codemirror/vue-next` | ^0.x | Vue 3 封装 | CodeMirror 6 的 Vue 3 组件 |
| `@ckpack/vue-color` | ^1 | 颜色选择器 | 像素取色后编辑颜色 |
| `vitest` | ^3 | 测试框架 | Vite 原生，速度快 |
| `@vue/test-utils` | ^2 | 组件测试 | Vue 3 官方 |
| `vue-tsc` | ^2 | 类型检查 | 替代 tsc，支持 .vue 文件 |
| `@tauri-apps/cli` | ^2 | Tauri CLI | 构建/开发命令 |
| `eslint` | ^9 | 代码检查 | 配合 @vue/eslint-config-typescript |
| `prettier` | ^3 | 代码格式化 | 统一前端风格 |

### 备选/待评估

| 包 | 场景 | 备注 |
|---|---|---|
| `PrimeVue` | 备选 UI 库 | 组件更多但更重，styled/unstyled 双模式 |
| `Element Plus` | 备选 UI 库 | 成熟但偏 Web，桌面感不如 Naive UI |
| `@guolao/vue-monaco-editor` | 备选编辑器 | Monaco 编辑器（VS Code 内核），功能强但 ~5MB |
| `lucide-vue-next` | 备选图标 | 更简洁，图标数量少于 Tabler |
| `UnoCSS` | 备选 CSS | 比 Tailwind 更快，但生态较小 |
