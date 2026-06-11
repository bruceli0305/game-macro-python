use crate::debug_task::DebugTaskRegistry;
use crate::engine_task::EngineTaskRegistry;
use tracing_subscriber::{EnvFilter, fmt};

pub mod ast;
pub mod capture;
mod commands;
pub mod debug_task;
pub mod engine;
pub mod engine_task;
pub mod error;
pub mod gw2;
pub mod input;
pub mod models;
pub mod profile;
pub mod store;

/// Application-wide shared state.
pub struct AppState {
    /// Active engine task, when the engine is running.
    pub engine_tasks: EngineTaskRegistry,
    /// Active one-shot debug task, when the debug panel is running.
    pub debug_tasks: DebugTaskRegistry,
}

pub fn run() {
    fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    tracing::info!("Game Macro Tauri started");

    let state = AppState {
        engine_tasks: EngineTaskRegistry::new(),
        debug_tasks: DebugTaskRegistry::new(),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            commands::engine_cmd::engine_start,
            commands::engine_cmd::engine_stop,
            commands::engine_cmd::engine_status,
            commands::engine_cmd::engine_preflight,
            commands::engine_cmd::simulate_rotation,
            commands::engine_cmd::simulate_rotation_with_pixels,
            commands::engine_cmd::simulate_profile_rotation,
            commands::engine_cmd::simulate_profile_rotation_with_pixels,
            commands::engine_cmd::simulate_ipc_smoke_fixture,
            commands::debug_cmd::open_debug_panel_window,
            commands::debug_cmd::debug_run_once,
            commands::debug_cmd::debug_stop_run,
            commands::profile_cmd::profile_list,
            commands::profile_cmd::profile_get_active,
            commands::profile_cmd::profile_set_active,
            commands::profile_cmd::profile_load,
            commands::profile_cmd::profile_save,
            commands::capture_cmd::capture_sample,
            commands::capture_cmd::capture_at_cursor,
            commands::capture_cmd::capture_diagnostics,
            commands::capture_cmd::capture_cast_bar_roi,
            commands::skill_cmd::gw2_skill_search,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Tauri application")
        .run(|_app_handle, _event| {});
}
