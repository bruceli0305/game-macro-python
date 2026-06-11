# Progress

## Goal
确认真实发键路径，并让桌面程序通过 Tauri 启动入口请求管理员权限。

## Done
- 确认真实执行路径使用 `EnigoKeySender`，通过 `enigo` 发送 press/release。
- 去掉真实引擎启动时的 no-op 发键降级：`enigo` 初始化失败时直接停止引擎并发送 `engine_start_failed` 日志。
- 增加 Windows `requireAdministrator` manifest。
- 将管理员 manifest 绑定到 `pnpm tauri ...` 入口，避免普通 `cargo test` 也被 UAC 阻断。

## Files Changed
- `src-tauri/src/input/key_sender.rs`：现有真实发键实现，未改动。
- `src-tauri/src/commands/engine_cmd.rs`：真实运行时发键器初始化失败改为 fail-fast。
- `src-tauri/build.rs`：按 `GAME_MACRO_ADMIN_MANIFEST=1` 切换管理员 manifest。
- `src-tauri/windows-admin.manifest`：Windows UAC manifest。
- `package.json`：`tauri` 脚本改为 Node 包装入口。
- `scripts/tauri-admin.mjs`：设置管理员 manifest 环境变量并转发到 Tauri CLI。

## Root Cause / Key Decision
直接在 `build.rs` 无条件嵌入管理员 manifest 会导致 `cargo test` 生成的 bin 测试程序也要求提权，非管理员终端报 Windows 740。最终采用脚本入口显式开启 manifest，保证桌面运行提权，同时保留普通测试能力。

## Logs / Tests
- `node scripts/tauri-admin.mjs --version`：通过，输出 `tauri-cli 2.11.2`。
- `cargo test`：通过，175 passed。
- `cargo clippy --no-default-features -- -D warnings`：通过。
- `pnpm.cmd build`：通过，保留既有 chunk size warning。

## Risks
- 只有通过 `pnpm tauri ...` 启动/构建时会请求管理员权限；直接 `cargo run` 不会开启管理员 manifest。
- 管理员 manifest 会在实际启动桌面 exe 时触发 UAC，需要用户确认。

## Next Step
后续可以增加一个运行前环境检查，在 UI 中明确展示当前进程是否管理员、真实发键器是否可用。
