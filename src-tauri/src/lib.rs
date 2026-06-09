use std::sync::Mutex;

use tauri::async_runtime::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing_subscriber::{EnvFilter, fmt};

pub mod ast;
pub mod capture;
mod commands;
pub mod engine;
pub mod error;
pub mod input;
pub mod models;
pub mod store;

/// Runtime handle for the active engine task.
pub struct EngineTaskHandle {
    cancel: CancellationToken,
    join: Option<JoinHandle<()>>,
}

impl EngineTaskHandle {
    /// Creates a task handle for a spawned engine loop.
    pub fn new(cancel: CancellationToken, join: JoinHandle<()>) -> Self {
        Self {
            cancel,
            join: Some(join),
        }
    }

    pub(crate) fn pending(cancel: CancellationToken) -> Self {
        Self { cancel, join: None }
    }

    #[cfg(test)]
    pub(crate) fn for_test(cancel: CancellationToken) -> Self {
        Self { cancel, join: None }
    }

    /// Requests cooperative shutdown.
    pub fn cancel(&self) {
        self.cancel.cancel();
    }

    /// Returns true when the cancellation token and join handle both look active.
    pub fn is_running(&self) -> bool {
        if self.cancel.is_cancelled() {
            return false;
        }

        if let Some(join) = &self.join {
            return !join.inner().is_finished();
        }

        true
    }
}

/// Application-wide shared state.
pub struct AppState {
    /// Active engine task, when the engine is running.
    pub engine_task: Mutex<Option<EngineTaskHandle>>,
}

pub fn run() {
    fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    tracing::info!("Game Macro Tauri started");

    let state = AppState {
        engine_task: Mutex::new(None),
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
            commands::profile_cmd::profile_list,
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
