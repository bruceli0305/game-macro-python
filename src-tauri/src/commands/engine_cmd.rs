//! Engine start, stop, status, and simulation commands.

use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};
use tokio_util::sync::CancellationToken;

use crate::AppState;
use crate::ast::evaluator::CastBarRoiProvider;
use crate::capture::capturer::CachedPixelSampler;
use crate::capture::cast_bar_roi::ScreenCastBarRoiProvider;
use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::profile_config::{
    EnginePreflightReport, load_active_engine_profile, load_active_preflight_report,
};
use crate::engine::runtime_payload::{RuntimePayloadInput, runtime_payload};
use crate::engine::simulation;
pub use crate::engine::simulation::PixelOverride;
use crate::engine::skill_attempt::{KeySender, SkillAttemptConfig};
use crate::engine_task::EngineTaskHandle;
use crate::error::CommandResult;
use crate::input::EnigoKeySender;
use crate::models::cycle::CycleConfig;
use crate::models::point::Point;
use crate::models::skill::Skill;

#[derive(Debug, Clone, Serialize)]
pub struct EngineStatus {
    pub running: bool,
}

#[derive(Debug, Clone, Serialize)]
struct EngineTickPayload {
    total_executed: u32,
    cycle_count: u32,
    phase_index: usize,
    phase_name: String,
    skill_id: String,
    skill_name: String,
    outcome: String,
}

fn emit_runtime_snapshot(
    app: &AppHandle,
    executor: &CycleExecutor<'_>,
    config: &CycleConfig,
    skills: &[Skill],
    uptime_ms: u64,
) {
    let payload = runtime_payload(RuntimePayloadInput {
        runtime: &executor.runtime,
        config,
        skills,
        total_executed: executor.state.total_executed,
        cycle_count: executor.state.cycle_count,
        phase_index: executor.state.phase_index,
        uptime_ms,
        cast_bar_roi: executor
            .cast_bar_roi
            .and_then(CastBarRoiProvider::get_cast_bar_roi_stats),
    });
    let _ = app.emit("engine:runtime", payload);
}

async fn run_engine_loop(
    app: AppHandle,
    cancel: CancellationToken,
    config: CycleConfig,
    skills: Vec<Skill>,
    points: Vec<Point>,
    attempt_cfg: SkillAttemptConfig,
) {
    let sampler = CachedPixelSampler::new();
    let roi_provider = attempt_cfg
        .cast_bar_roi
        .clone()
        .map(|cfg| ScreenCastBarRoiProvider::with_shared_sampler(cfg, &sampler));
    let mut executor = CycleExecutor::new(&config, &points, &skills, &sampler, attempt_cfg)
        .with_cast_bar_roi_provider(
            roi_provider
                .as_ref()
                .map(|provider| provider as &dyn CastBarRoiProvider),
        );

    let mut key_sender: Box<dyn KeySender> = match EnigoKeySender::new() {
        Ok(sender) => {
            tracing::info!("engine key sender initialized with enigo");
            Box::new(sender)
        }
        Err(error) => {
            let reason = format!("key sender unavailable: {error}");
            tracing::error!(reason = %reason, "engine failed to initialize key sender");
            executor.runtime.engine_stopped(&reason);
            let _ = app.emit(
                "engine:log",
                serde_json::json!({ "event": "engine_start_failed", "reason": reason }),
            );
            let _ = app.emit("engine:stopped", EngineStatus { running: false });
            emit_runtime_snapshot(&app, &executor, &config, &skills, 0);
            return;
        }
    };

    let start = Instant::now();
    let mut last_log_emit = Instant::now();
    let mut last_runtime_emit = Instant::now();

    executor.runtime.engine_started(&config.name);
    let _ = executor.reacquire_phase_from_current_frame(0);
    let _ = app.emit("engine:started", EngineStatus { running: true });
    emit_runtime_snapshot(&app, &executor, &config, &skills, 0);

    loop {
        if cancel.is_cancelled() {
            break;
        }

        let elapsed_ms = start.elapsed().as_millis() as u64;
        let acted = executor.tick(key_sender.as_mut(), &|| cancel.is_cancelled(), elapsed_ms);

        if acted {
            let phase = config.phases.get(
                executor
                    .state
                    .phase_index
                    .min(config.phases.len().saturating_sub(1)),
            );
            let phase_name = phase.map(|p| p.name.as_str()).unwrap_or("complete");
            let last_skill_name = skills
                .iter()
                .find(|skill| skill.id == executor.state.last_skill_id)
                .map(|skill| skill.name.as_str())
                .unwrap_or("");

            let _ = app.emit(
                "engine:tick",
                EngineTickPayload {
                    total_executed: executor.state.total_executed,
                    cycle_count: executor.state.cycle_count,
                    phase_index: executor.state.phase_index,
                    phase_name: phase_name.into(),
                    skill_id: executor.state.last_skill_id.clone(),
                    skill_name: last_skill_name.into(),
                    outcome: executor.state.last_outcome.clone(),
                },
            );
        }

        if acted || last_runtime_emit.elapsed().as_millis() > 500 {
            emit_runtime_snapshot(&app, &executor, &config, &skills, elapsed_ms);
            last_runtime_emit = Instant::now();
        }

        if last_log_emit.elapsed().as_millis() > 500 && !executor.log.is_empty() {
            for log in &executor.log {
                let _ = app.emit(
                    "engine:log",
                    serde_json::json!({
                        "ts_ms": log.ts_ms,
                        "phase_name": log.phase_name,
                        "event": log.event,
                        "skill_id": log.skill_id,
                        "skill_name": log.skill_name,
                        "outcome": log.outcome,
                        "reason": log.reason,
                    }),
                );
            }
            executor.log.clear();
            last_log_emit = Instant::now();
        }

        let poll_delay = Duration::from_millis(config.poll_interval_ms as u64);
        tokio::select! {
            () = cancel.cancelled() => break,
            () = tokio::time::sleep(poll_delay) => {}
        }
    }

    executor.runtime.engine_stopped("cancelled");
    let _ = app.emit("engine:stopped", EngineStatus { running: false });
    emit_runtime_snapshot(
        &app,
        &executor,
        &config,
        &skills,
        start.elapsed().as_millis() as u64,
    );
    tracing::info!("engine loop exited");
}

#[tauri::command]
pub fn engine_preflight(state: State<'_, AppState>) -> CommandResult<EnginePreflightReport> {
    let engine_running = state.engine_tasks.is_running()?;
    Ok(load_active_preflight_report(engine_running)?)
}

#[tauri::command]
pub fn engine_start(app: AppHandle, state: State<'_, AppState>) -> CommandResult<String> {
    let reservation = state.engine_tasks.reserve()?;

    let input = match load_active_engine_profile(true) {
        Ok(input) => input,
        Err(error) => {
            state.engine_tasks.cancel_reservation(&reservation)?;
            return Err(error.into());
        }
    };

    if reservation.is_cancelled() {
        return Ok("stopped".into());
    }

    let task_cancel = reservation.cancel_token();
    let (start_tx, start_rx) = tokio::sync::oneshot::channel::<()>();
    let join = tauri::async_runtime::spawn(async move {
        if start_rx.await.is_err() || task_cancel.is_cancelled() {
            return;
        }
        run_engine_loop(
            app,
            task_cancel,
            input.config,
            input.skills,
            input.points,
            input.attempt_cfg,
        )
        .await;
    });
    let task = EngineTaskHandle::new(reservation.id(), reservation.cancel_token(), join);
    if !state.engine_tasks.install(&reservation, task)? {
        tracing::info!("engine start cancelled before task install");
        return Ok("stopped".into());
    }
    let _ = start_tx.send(());

    tracing::info!("engine started");
    Ok("started".into())
}

#[tauri::command]
pub async fn engine_stop(state: State<'_, AppState>) -> CommandResult<String> {
    let task = state.engine_tasks.take()?;

    if let Some(task) = task {
        task.cancel();
        tracing::info!("engine stopping");
        task.shutdown().await;
        tracing::info!("engine stopped");
    }

    Ok("stopped".into())
}

#[tauri::command]
pub fn simulate_rotation() -> CommandResult<String> {
    Ok(simulation::simulate_active_rotation()?)
}

#[tauri::command]
pub fn simulate_rotation_with_pixels(pixel_overrides: Vec<PixelOverride>) -> CommandResult<String> {
    Ok(simulation::simulate_active_rotation_with_pixels(
        pixel_overrides,
    )?)
}

#[tauri::command]
pub fn simulate_profile_rotation(content: String) -> CommandResult<String> {
    Ok(simulation::simulate_profile_rotation(content)?)
}

#[tauri::command]
pub fn simulate_profile_rotation_with_pixels(
    content: String,
    pixel_overrides: Vec<PixelOverride>,
) -> CommandResult<String> {
    Ok(simulation::simulate_profile_rotation_with_pixels(
        content,
        pixel_overrides,
    )?)
}

#[tauri::command]
pub fn simulate_ipc_smoke_fixture() -> CommandResult<String> {
    Ok(simulation::simulate_ipc_smoke_fixture()?)
}

#[tauri::command]
pub fn engine_status(state: State<'_, AppState>) -> CommandResult<EngineStatus> {
    Ok(EngineStatus {
        running: state.engine_tasks.is_running()?,
    })
}

#[cfg(test)]
#[path = "engine_cmd_tests.rs"]
mod tests;
