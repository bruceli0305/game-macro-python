//! Engine start, stop, status, and simulation commands.

use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};
use tokio_util::sync::CancellationToken;

use crate::capture::capturer::DirectPixelSampler;
use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::runtime_state::{AttemptStage, RuntimeState};
use crate::engine::skill_attempt::{KeySender, SkillAttemptConfig};
use crate::error::{AppError, AppResult, CommandResult};
use crate::input::EnigoKeySender;
use crate::models::cycle::CycleConfig;
use crate::models::point::Point;
use crate::models::skill::Skill;
use crate::store::profile_store::ProfileStore;
use crate::{AppState, EngineTaskHandle};

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

#[derive(Debug, Clone, Serialize)]
struct EngineRuntimePayload {
    running: bool,
    paused: bool,
    preset_id: String,
    stop_reason: String,
    total_executed: u32,
    cycle_count: u32,
    phase_index: usize,
    phase_name: String,
    uptime_ms: u64,
    skills: Vec<SkillRuntimePayload>,
}

#[derive(Debug, Clone, Serialize)]
struct SkillRuntimePayload {
    skill_id: String,
    skill_name: String,
    state: String,
    node_exec: u32,
    ready_false: u32,
    skipped_disabled: u32,
    skipped_lock_busy: u32,
    attempt_started: u32,
    key_sent_ok: u32,
    cast_started: u32,
    success: u32,
    fail: u32,
}

fn load_profile_config() -> AppResult<(CycleConfig, Vec<Skill>, Vec<Point>)> {
    let dir = app_data_dir()?;
    let store = ProfileStore::new(dir);
    let profile = store.load("default")?;

    let config = profile
        .rotations
        .into_iter()
        .next()
        .ok_or_else(|| AppError::Config("default profile has no rotations".into()))?;
    let skills = profile.skills.skills;
    let points = profile.points.points;

    tracing::info!(
        "loaded profile 'default': {} phases, {} skills",
        config.phases.len(),
        skills.len()
    );

    Ok((config, skills, points))
}

fn app_data_dir() -> AppResult<std::path::PathBuf> {
    #[cfg(target_os = "windows")]
    {
        let local = std::env::var("LOCALAPPDATA")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("."));
        Ok(local.join("game-macro-tauri"))
    }
    #[cfg(not(target_os = "windows"))]
    {
        let dir = dirs::data_dir()
            .ok_or_else(|| AppError::Config("unable to determine data directory".into()))?;
        Ok(dir.join("game-macro-tauri"))
    }
}

fn engine_lock_error(error: impl std::fmt::Display) -> AppError {
    AppError::Engine(format!("engine state lock failed: {error}"))
}

fn task_is_running(task: Option<&EngineTaskHandle>) -> bool {
    task.is_some_and(EngineTaskHandle::is_running)
}

fn ensure_engine_stopped(engine_task: &Mutex<Option<EngineTaskHandle>>) -> AppResult<()> {
    let guard = engine_task.lock().map_err(engine_lock_error)?;
    if task_is_running(guard.as_ref()) {
        return Err(AppError::Engine("engine already running".into()));
    }
    Ok(())
}

fn reserve_engine_task(
    engine_task: &Mutex<Option<EngineTaskHandle>>,
    task: EngineTaskHandle,
) -> AppResult<()> {
    let mut guard = engine_task.lock().map_err(engine_lock_error)?;
    if task_is_running(guard.as_ref()) {
        return Err(AppError::Engine("engine already running".into()));
    }
    *guard = Some(task);
    Ok(())
}

fn take_engine_task(
    engine_task: &Mutex<Option<EngineTaskHandle>>,
) -> AppResult<Option<EngineTaskHandle>> {
    let mut guard = engine_task.lock().map_err(engine_lock_error)?;
    Ok(guard.take())
}

fn replace_engine_task(
    engine_task: &Mutex<Option<EngineTaskHandle>>,
    task: EngineTaskHandle,
) -> AppResult<()> {
    let mut guard = engine_task.lock().map_err(engine_lock_error)?;
    *guard = Some(task);
    Ok(())
}

fn stage_label(stage: AttemptStage) -> &'static str {
    match stage {
        AttemptStage::Idle => "IDLE",
        AttemptStage::Preparing => "PREPARING",
        AttemptStage::StartWait => "START_WAIT",
        AttemptStage::Casting => "CASTING",
        AttemptStage::CompleteWait => "COMPLETE_WAIT",
        AttemptStage::Success => "SUCCESS",
        AttemptStage::Failed => "FAILED",
        AttemptStage::Stopped => "STOPPED",
    }
}

fn runtime_payload(
    runtime: &RuntimeState,
    config: &CycleConfig,
    skills: &[Skill],
    total_executed: u32,
    cycle_count: u32,
    phase_index: usize,
    uptime_ms: u64,
) -> EngineRuntimePayload {
    let phase_name = config
        .phases
        .get(phase_index.min(config.phases.len().saturating_sub(1)))
        .map(|phase| phase.name.as_str())
        .unwrap_or("complete")
        .to_string();

    let mut skill_payloads: Vec<_> = runtime
        .skills
        .values()
        .map(|state| {
            let skill_name = skills
                .iter()
                .find(|skill| skill.id == state.skill_id)
                .map(|skill| skill.name.as_str())
                .unwrap_or("");

            SkillRuntimePayload {
                skill_id: state.skill_id.clone(),
                skill_name: skill_name.into(),
                state: stage_label(state.current_stage).into(),
                node_exec: state.node_exec,
                ready_false: state.ready_false,
                skipped_disabled: state.skipped_disabled,
                skipped_lock_busy: state.skipped_lock_busy,
                attempt_started: state.attempt_started,
                key_sent_ok: state.key_sent_ok,
                cast_started: state.cast_started,
                success: state.success,
                fail: state.fail,
            }
        })
        .collect();
    skill_payloads.sort_by(|left, right| left.skill_id.cmp(&right.skill_id));

    EngineRuntimePayload {
        running: runtime.engine.running,
        paused: runtime.engine.paused,
        preset_id: runtime.engine.preset_id.clone(),
        stop_reason: runtime.engine.stop_reason.clone(),
        total_executed,
        cycle_count,
        phase_index,
        phase_name,
        uptime_ms,
        skills: skill_payloads,
    }
}

fn emit_runtime_snapshot(
    app: &AppHandle,
    executor: &CycleExecutor<'_>,
    config: &CycleConfig,
    skills: &[Skill],
    uptime_ms: u64,
) {
    let payload = runtime_payload(
        &executor.runtime,
        config,
        skills,
        executor.state.total_executed,
        executor.state.cycle_count,
        executor.state.phase_index,
        uptime_ms,
    );
    let _ = app.emit("engine:runtime", payload);
}

async fn run_engine_loop(
    app: AppHandle,
    cancel: CancellationToken,
    config: CycleConfig,
    skills: Vec<Skill>,
    points: Vec<Point>,
) {
    let sampler = DirectPixelSampler;
    let attempt_cfg = SkillAttemptConfig::default();
    let mut executor = CycleExecutor::new(&config, &points, &skills, &sampler, attempt_cfg);

    let mut key_sender: Box<dyn KeySender> = match EnigoKeySender::new() {
        Ok(sender) => {
            tracing::info!("engine key sender initialized with enigo");
            Box::new(sender)
        }
        Err(error) => {
            tracing::warn!("enigo unavailable ({error}); using noop key sender");

            struct NoopSender;
            impl KeySender for NoopSender {
                fn send_key(&mut self, _key: &str) -> bool {
                    true
                }
            }

            Box::new(NoopSender)
        }
    };

    let start = Instant::now();
    let mut last_log_emit = Instant::now();
    let mut last_runtime_emit = Instant::now();

    executor.runtime.engine_started(&config.name);
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
pub fn engine_start(app: AppHandle, state: State<'_, AppState>) -> CommandResult<String> {
    ensure_engine_stopped(&state.engine_task)?;

    let cancel = CancellationToken::new();
    reserve_engine_task(
        &state.engine_task,
        EngineTaskHandle::pending(cancel.clone()),
    )?;

    let (config, skills, points) = match load_profile_config() {
        Ok(config) => config,
        Err(error) => {
            if let Some(task) = take_engine_task(&state.engine_task)? {
                task.cancel();
            }
            return Err(error.into());
        }
    };

    if cancel.is_cancelled() {
        return Ok("stopped".into());
    }

    let task_cancel = cancel.clone();
    let join = tauri::async_runtime::spawn(async move {
        run_engine_loop(app, task_cancel, config, skills, points).await;
    });
    let task = EngineTaskHandle::new(cancel, join);
    replace_engine_task(&state.engine_task, task)?;

    tracing::info!("engine started");
    Ok("started".into())
}

#[tauri::command]
pub fn engine_stop(state: State<'_, AppState>) -> CommandResult<String> {
    let task = take_engine_task(&state.engine_task)?;

    if let Some(task) = task {
        task.cancel();
        tracing::info!("engine stopping");
    }

    Ok("stopped".into())
}

#[tauri::command]
pub fn simulate_rotation() -> CommandResult<String> {
    let (config, skills, points) = load_profile_config()?;

    let sampler = DirectPixelSampler;
    let attempt_cfg = SkillAttemptConfig::default();
    let mut executor = CycleExecutor::new(&config, &points, &skills, &sampler, attempt_cfg);

    struct NoopKeySender;
    impl KeySender for NoopKeySender {
        fn send_key(&mut self, _: &str) -> bool {
            true
        }
    }
    let mut key_sender = NoopKeySender;

    let mut sim_events: Vec<serde_json::Value> = Vec::new();
    let max_ticks = 80;
    let mut time_ms: u64 = 0;

    for _tick in 0..max_ticks {
        let acted = executor.tick(&mut key_sender, &|| false, time_ms);
        if acted {
            let phase_name = config
                .phases
                .get(
                    executor
                        .state
                        .phase_index
                        .min(config.phases.len().saturating_sub(1)),
                )
                .map(|phase| phase.name.as_str())
                .unwrap_or("complete");
            let skill_name = skills
                .iter()
                .find(|skill| skill.id == executor.state.last_skill_id)
                .map(|skill| skill.name.as_str())
                .unwrap_or("");

            let skill = skills
                .iter()
                .find(|skill| skill.id == executor.state.last_skill_id);
            let cast_ms = skill.map(|skill| skill.cast.readbar_ms).unwrap_or(0) as u64;
            let cd_ms = skill.map(|skill| skill.cooldown_ms).unwrap_or(0) as u64;
            let gap = 50_u64;

            sim_events.push(serde_json::json!({
                "index": executor.state.total_executed,
                "timeMs": time_ms,
                "phase": phase_name,
                "skillId": executor.state.last_skill_id,
                "skillName": skill_name,
                "outcome": executor.state.last_outcome,
                "castMs": cast_ms,
                "cdMs": cd_ms,
                "reason": "",
            }));

            time_ms += cast_ms.max(1) + gap;
        } else {
            time_ms += config.poll_interval_ms as u64;
        }
    }

    serde_json::to_string_pretty(&serde_json::json!({ "events": sim_events }))
        .map_err(AppError::from)
        .map_err(Into::into)
}

#[tauri::command]
pub fn engine_status(state: State<'_, AppState>) -> CommandResult<EngineStatus> {
    let guard = state.engine_task.lock().map_err(engine_lock_error)?;
    Ok(EngineStatus {
        running: task_is_running(guard.as_ref()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_running_token_blocks_reserve() {
        let state = Mutex::new(Some(EngineTaskHandle::for_test(CancellationToken::new())));

        assert!(matches!(
            ensure_engine_stopped(&state),
            Err(AppError::Engine(_))
        ));
        assert!(matches!(
            reserve_engine_task(&state, EngineTaskHandle::for_test(CancellationToken::new())),
            Err(AppError::Engine(_))
        ));
    }

    #[test]
    fn test_cancelled_token_can_be_replaced() {
        let old = CancellationToken::new();
        old.cancel();
        let state = Mutex::new(Some(EngineTaskHandle::for_test(old)));

        assert!(ensure_engine_stopped(&state).is_ok());
        let new = CancellationToken::new();
        reserve_engine_task(&state, EngineTaskHandle::for_test(new)).unwrap();

        let guard = state.lock().unwrap();
        assert!(task_is_running(guard.as_ref()));
    }

    #[test]
    fn test_runtime_payload_maps_skill_metrics() {
        let config = CycleConfig {
            name: "default".into(),
            phases: vec![],
            poll_interval_ms: 100,
            max_cycles: 0,
        };
        let mut runtime = RuntimeState::new();
        runtime.engine_started("default");
        runtime.mark_attempt_started("skill-1");
        runtime.mark_success("skill-1");

        let payload = runtime_payload(&runtime, &config, &[], 1, 2, 0, 123);

        assert!(payload.running);
        assert_eq!(payload.total_executed, 1);
        assert_eq!(payload.cycle_count, 2);
        assert_eq!(payload.uptime_ms, 123);
        assert_eq!(payload.skills.len(), 1);
        assert_eq!(payload.skills[0].skill_id, "skill-1");
        assert_eq!(payload.skills[0].state, "SUCCESS");
        assert_eq!(payload.skills[0].attempt_started, 1);
        assert_eq!(payload.skills[0].success, 1);
    }
}
