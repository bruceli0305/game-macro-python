//! Debug panel window and one-shot debug run commands.

use tauri::{AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder};
use uuid::Uuid;

use crate::AppState;
use crate::debug_task::DebugTaskHandle;
use crate::engine::debug_runner::{
    DebugRunEvent, DebugRunFinishedPayload, DebugRunRequest, DebugRunStartedPayload,
    run_debug_once_with_real_input, validate_debug_phase_range,
};
use crate::engine::profile_config::load_active_engine_profile;
use crate::error::{AppError, CommandResult};

const DEBUG_PANEL_LABEL: &str = "debug-panel";

#[tauri::command]
pub fn open_debug_panel_window(app: AppHandle) -> CommandResult<String> {
    if let Some(window) = app.get_webview_window(DEBUG_PANEL_LABEL) {
        window.show().map_err(window_error)?;
        window.set_focus().map_err(window_error)?;
        window.set_always_on_top(true).map_err(window_error)?;
        return Ok("focused".into());
    }

    WebviewWindowBuilder::new(
        &app,
        DEBUG_PANEL_LABEL,
        WebviewUrl::App("index.html?debugPanel=1".into()),
    )
    .title("循环调试面板")
    .inner_size(420.0, 560.0)
    .min_inner_size(360.0, 420.0)
    .resizable(true)
    .always_on_top(true)
    .build()
    .map_err(window_error)?;

    Ok("opened".into())
}

#[tauri::command]
pub fn debug_run_once(
    app: AppHandle,
    state: State<'_, AppState>,
    start_phase_index: usize,
    end_phase_index: usize,
) -> CommandResult<String> {
    if state.engine_tasks.is_running()? {
        return Err(AppError::Engine("engine already running".into()).into());
    }

    let reservation = state.debug_tasks.reserve()?;
    let request = DebugRunRequest {
        start_phase_index,
        end_phase_index,
    };

    let input = match load_active_engine_profile(true) {
        Ok(input) => input,
        Err(error) => {
            state.debug_tasks.cancel_reservation(&reservation)?;
            return Err(error.into());
        }
    };

    if let Err(error) = validate_debug_phase_range(&input.config, &request) {
        state.debug_tasks.cancel_reservation(&reservation)?;
        return Err(error.into());
    }

    let run_id = Uuid::new_v4().to_string();
    let started = DebugRunStartedPayload {
        run_id: run_id.clone(),
        start_phase_index,
        end_phase_index,
        started_at_ms: 0,
    };
    let _ = app.emit("debug:run-started", started);

    let task_cancel = reservation.cancel_token();
    let run_id_for_task = run_id.clone();
    let join = tauri::async_runtime::spawn(async move {
        let app_for_events = app.clone();
        let run_result = run_debug_once_with_real_input(
            run_id_for_task.clone(),
            input,
            request,
            task_cancel.clone(),
            move |event| match event {
                DebugRunEvent::Event(payload) => {
                    let _ = app_for_events.emit("debug:run-event", payload);
                }
                DebugRunEvent::Finished(payload) => {
                    let event_name = match payload.status.as_str() {
                        "stopped" => "debug:run-stopped",
                        "failed" => "debug:run-failed",
                        _ => "debug:run-finished",
                    };
                    let _ = app_for_events.emit(event_name, payload);
                }
            },
        )
        .await;

        if let Err(error) = run_result {
            let payload = DebugRunFinishedPayload {
                run_id: run_id_for_task.clone(),
                status: "failed".into(),
                reason: error.to_string(),
                elapsed_ms: 0,
                total_events: 0,
            };
            let _ = app.emit("debug:run-failed", payload);
        }
    });

    let task = DebugTaskHandle::new(reservation.id(), reservation.cancel_token(), join);
    if !state.debug_tasks.install(&reservation, task)? {
        tracing::info!("debug run cancelled before task install");
        return Ok("stopped".into());
    }

    Ok(run_id)
}

#[tauri::command]
pub async fn debug_stop_run(state: State<'_, AppState>) -> CommandResult<String> {
    let task = state.debug_tasks.take()?;
    if let Some(task) = task {
        task.cancel();
        task.shutdown().await;
    }
    Ok("stopped".into())
}

fn window_error(error: tauri::Error) -> AppError {
    AppError::Engine(format!("debug panel window error: {error}"))
}
