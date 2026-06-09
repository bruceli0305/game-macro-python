//! Engine start, stop, status, and simulation commands.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};
use tokio_util::sync::CancellationToken;

use crate::ast::evaluator::{CastBarRoiProvider, CastBarRoiStats, PixelSampler};
use crate::capture::capturer::{CachedPixelSampler, DirectPixelSampler};
use crate::capture::cast_bar_roi::ScreenCastBarRoiProvider;
use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::runtime_state::{AttemptStage, RuntimeState};
use crate::engine::skill_attempt::{KeySender, SkillAttemptConfig};
use crate::error::{AppError, AppResult, CommandResult};
use crate::input::EnigoKeySender;
use crate::models::base::BaseConfig;
use crate::models::cycle::{CycleConfig, CyclePhase, SkillSlot};
use crate::models::point::Point;
use crate::models::profile::Profile;
use crate::models::skill::{CastConfig, ColorRGB, PixelSpec, SampleConfig, Skill};
use crate::store::profile_store::{ProfileStore, default_profile};
use crate::{AppState, EngineTaskHandle};

#[derive(Debug, Clone, Serialize)]
pub struct EngineStatus {
    pub running: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct EnginePreflightReport {
    pub ready: bool,
    pub engine_running: bool,
    pub profile_name: String,
    pub exec_enabled: bool,
    pub rotation_count: usize,
    pub skill_count: usize,
    pub point_count: usize,
    pub executable_slot_count: usize,
    pub error: Option<String>,
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
    cast_bar_roi: Option<CastBarRoiRuntimePayload>,
    skills: Vec<SkillRuntimePayload>,
}

#[derive(Debug, Clone, Serialize)]
struct CastBarRoiRuntimePayload {
    enabled: bool,
    sample_count: u64,
    cache_hit_count: u64,
    failed_sample_count: u64,
    last_latency_us: u64,
    avg_latency_us: u64,
    max_latency_us: u64,
    last_changed_ratio: f64,
    last_border_match_ratio: f64,
    last_changed_from_baseline: bool,
    last_border_visible: bool,
    last_gone: bool,
    last_error: String,
}

struct RuntimePayloadInput<'a> {
    runtime: &'a RuntimeState,
    config: &'a CycleConfig,
    skills: &'a [Skill],
    total_executed: u32,
    cycle_count: u32,
    phase_index: usize,
    uptime_ms: u64,
    cast_bar_roi: Option<CastBarRoiStats>,
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

#[derive(Debug, Clone, Deserialize)]
pub struct PixelOverride {
    monitor: String,
    x: i32,
    y: i32,
    r: u8,
    g: u8,
    b: u8,
}

struct OverridePixelSampler {
    pixels: HashMap<(String, i32, i32), (u8, u8, u8)>,
}

#[derive(Debug, Clone, Serialize)]
struct IpcSmokeFixtureSummary {
    profile_id: String,
    direct_events: usize,
    pixel_events: usize,
}

impl OverridePixelSampler {
    fn new(overrides: Vec<PixelOverride>) -> Self {
        let pixels = overrides
            .into_iter()
            .map(|item| ((item.monitor, item.x, item.y), (item.r, item.g, item.b)))
            .collect();
        Self { pixels }
    }
}

impl PixelSampler for OverridePixelSampler {
    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        _sample_mode: &str,
        _sample_radius: u8,
    ) -> Option<(u8, u8, u8)> {
        self.pixels
            .get(&(monitor.to_string(), x_abs, y_abs))
            .copied()
    }
}

fn load_profile_config(
    require_exec_enabled: bool,
) -> AppResult<(CycleConfig, Vec<Skill>, Vec<Point>, SkillAttemptConfig)> {
    let dir = app_data_dir()?;
    let store = ProfileStore::new(dir);
    let (profile_name, profile) = store.load_active_or_default()?;

    validate_engine_profile(&profile, require_exec_enabled)?;
    let attempt_cfg = attempt_config_from_base(&profile.base);

    let config =
        profile.rotations.into_iter().next().ok_or_else(|| {
            AppError::Config(format!("profile '{profile_name}' has no rotations"))
        })?;
    let skills = profile.skills.skills;
    let points = profile.points.points;

    tracing::info!(
        "loaded profile '{}': {} phases, {} skills",
        profile_name,
        config.phases.len(),
        skills.len()
    );

    Ok((config, skills, points, attempt_cfg))
}

fn simulation_inputs_from_profile(
    profile: Profile,
) -> AppResult<(CycleConfig, Vec<Skill>, Vec<Point>, SkillAttemptConfig)> {
    validate_engine_profile(&profile, false)?;
    let attempt_cfg = attempt_config_from_base(&profile.base);

    let config = profile
        .rotations
        .into_iter()
        .next()
        .ok_or_else(|| AppError::Config("profile has no rotations".into()))?;

    Ok((
        config,
        profile.skills.skills,
        profile.points.points,
        attempt_cfg,
    ))
}

fn parse_profile_content(content: &str) -> AppResult<Profile> {
    serde_json::from_str(content).map_err(AppError::from)
}

fn event_count_from_simulation_json(content: &str) -> AppResult<usize> {
    let value: serde_json::Value = serde_json::from_str(content)?;
    let events = value
        .get("events")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| AppError::Engine("simulation response missing events array".into()))?;
    Ok(events.len())
}

fn smoke_fixture_profile() -> Profile {
    let mut profile = default_profile("ipc-smoke");
    profile.points.points = vec![Point {
        id: "smoke-point".into(),
        name: "IPC smoke point".into(),
        monitor: "primary".into(),
        vx: 10,
        vy: 20,
        color: ColorRGB {
            r: 12,
            g: 34,
            b: 56,
        },
        tolerance: 0,
        sample: SampleConfig {
            mode: "single".into(),
            radius: 0,
        },
        captured_at: "ipc-smoke".into(),
        note: "IPC smoke fixture".into(),
    }];
    profile.skills.skills = vec![Skill {
        id: "smoke-skill".into(),
        name: "IPC smoke skill".into(),
        enabled: true,
        trigger_key: "1".into(),
        cast: CastConfig {
            readbar_ms: 0,
            cooldown_ms: 0,
        },
        pixel: PixelSpec {
            monitor: "primary".into(),
            vx: 30,
            vy: 40,
            color: ColorRGB {
                r: 90,
                g: 120,
                b: 150,
            },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
        },
        note: "IPC smoke fixture".into(),
        game_id: 0,
        game_desc: String::new(),
        icon_url: String::new(),
        cooldown_ms: 0,
        radius: 0,
        shots_per_cycle: 1,
        ammo_stages: vec![],
    }];
    profile.rotations = vec![CycleConfig {
        name: "IPC smoke rotation".into(),
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 1,
        state_schema: None,
        phases: vec![CyclePhase {
            name: "P1".into(),
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
            skills: vec![SkillSlot {
                skill_id: "smoke-skill".into(),
                priority: 1,
                label: "smoke-skill".into(),
                condition_expr: Some(serde_json::json!({
                    "type": "pixel_point",
                    "point_id": "smoke-point",
                    "tolerance": 0
                })),
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
        }],
    }];
    profile
}

fn smoke_fixture_pixel_overrides() -> Vec<PixelOverride> {
    vec![PixelOverride {
        monitor: "primary".into(),
        x: 10,
        y: 20,
        r: 12,
        g: 34,
        b: 56,
    }]
}

fn attempt_config_from_base(base: &BaseConfig) -> SkillAttemptConfig {
    let cast_bar_roi =
        (base.cast_bar.roi.enabled || base.cast_bar.mode.trim() == "roi").then(|| {
            let mut roi = base.cast_bar.roi.clone();
            if base.cast_bar.mode.trim() == "roi" {
                roi.enabled = true;
            }
            roi
        });
    SkillAttemptConfig {
        default_gap_ms: base.exec.default_skill_gap_ms,
        poll_not_ready_ms: base.exec.poll_not_ready_ms,
        max_retries: base.exec.max_retries,
        retry_gap_ms: base.exec.retry_gap_ms,
        complete_poll_ms: base.cast_bar.poll_interval_ms,
        complete_max_wait_factor: base.cast_bar.max_wait_factor,
        cast_bar_roi,
        ..SkillAttemptConfig::default()
    }
}

fn validate_engine_profile(profile: &Profile, require_exec_enabled: bool) -> AppResult<()> {
    if require_exec_enabled && !profile.base.exec.enabled {
        return Err(AppError::Config(
            "macro execution is disabled in base.exec.enabled".into(),
        ));
    }

    let rotation = profile
        .rotations
        .first()
        .ok_or_else(|| AppError::Config("profile has no rotations".into()))?;
    if rotation.phases.is_empty() {
        return Err(AppError::Config("rotation has no phases".to_string()));
    }

    let mut has_executable_slot = false;
    for phase in &rotation.phases {
        for slot in &phase.skills {
            let skill_id = slot.skill_id.trim();
            if skill_id.is_empty() {
                continue;
            }
            let Some(skill) = profile
                .skills
                .skills
                .iter()
                .find(|skill| skill.id.as_str() == skill_id)
            else {
                return Err(AppError::Config(format!(
                    "slot references missing skill '{skill_id}'"
                )));
            };
            if !skill.enabled {
                continue;
            }
            if skill.trigger_key.trim().is_empty() {
                return Err(AppError::Config(format!(
                    "enabled skill '{}' has no trigger_key",
                    skill.id
                )));
            }
            has_executable_slot = true;
        }
    }

    if !has_executable_slot {
        return Err(AppError::Config(
            "rotation has no executable enabled skill slots".into(),
        ));
    }

    Ok(())
}

fn count_executable_slots(profile: &Profile) -> usize {
    let Some(rotation) = profile.rotations.first() else {
        return 0;
    };

    rotation
        .phases
        .iter()
        .flat_map(|phase| phase.skills.iter())
        .filter(|slot| {
            let skill_id = slot.skill_id.trim();
            if skill_id.is_empty() {
                return false;
            }
            profile.skills.skills.iter().any(|skill| {
                skill.id.as_str() == skill_id
                    && skill.enabled
                    && !skill.trigger_key.trim().is_empty()
            })
        })
        .count()
}

fn preflight_report_from_profile(profile: &Profile, engine_running: bool) -> EnginePreflightReport {
    let validation = validate_engine_profile(profile, true);
    EnginePreflightReport {
        ready: validation.is_ok() && !engine_running,
        engine_running,
        profile_name: profile.meta.profile_name.clone(),
        exec_enabled: profile.base.exec.enabled,
        rotation_count: profile.rotations.len(),
        skill_count: profile.skills.skills.len(),
        point_count: profile.points.points.len(),
        executable_slot_count: count_executable_slots(profile),
        error: if engine_running {
            Some("engine already running".into())
        } else {
            validation.err().map(|error| error.to_string())
        },
    }
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

fn runtime_payload(input: RuntimePayloadInput<'_>) -> EngineRuntimePayload {
    let phase_name = input
        .config
        .phases
        .get(
            input
                .phase_index
                .min(input.config.phases.len().saturating_sub(1)),
        )
        .map(|phase| phase.name.as_str())
        .unwrap_or("complete")
        .to_string();

    let mut skill_payloads: Vec<_> = input
        .runtime
        .skills
        .values()
        .map(|state| {
            let skill_name = input
                .skills
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
        running: input.runtime.engine.running,
        paused: input.runtime.engine.paused,
        preset_id: input.runtime.engine.preset_id.clone(),
        stop_reason: input.runtime.engine.stop_reason.clone(),
        total_executed: input.total_executed,
        cycle_count: input.cycle_count,
        phase_index: input.phase_index,
        phase_name,
        uptime_ms: input.uptime_ms,
        cast_bar_roi: input.cast_bar_roi.map(CastBarRoiRuntimePayload::from),
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

impl From<CastBarRoiStats> for CastBarRoiRuntimePayload {
    fn from(stats: CastBarRoiStats) -> Self {
        Self {
            enabled: stats.enabled,
            sample_count: stats.sample_count,
            cache_hit_count: stats.cache_hit_count,
            failed_sample_count: stats.failed_sample_count,
            last_latency_us: stats.last_latency_us,
            avg_latency_us: stats.avg_latency_us,
            max_latency_us: stats.max_latency_us,
            last_changed_ratio: stats.last_changed_ratio,
            last_border_match_ratio: stats.last_border_match_ratio,
            last_changed_from_baseline: stats.last_changed_from_baseline,
            last_border_visible: stats.last_border_visible,
            last_gone: stats.last_gone,
            last_error: stats.last_error,
        }
    }
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
        .map(ScreenCastBarRoiProvider::new);
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
pub fn engine_preflight(state: State<'_, AppState>) -> CommandResult<EnginePreflightReport> {
    let dir = app_data_dir()?;
    let store = ProfileStore::new(dir);
    let (_profile_name, profile) = store.load_active_or_default()?;
    let guard = state.engine_task.lock().map_err(engine_lock_error)?;
    let engine_running = task_is_running(guard.as_ref());

    Ok(preflight_report_from_profile(&profile, engine_running))
}

#[tauri::command]
pub fn engine_start(app: AppHandle, state: State<'_, AppState>) -> CommandResult<String> {
    ensure_engine_stopped(&state.engine_task)?;

    let cancel = CancellationToken::new();
    reserve_engine_task(
        &state.engine_task,
        EngineTaskHandle::pending(cancel.clone()),
    )?;

    let (config, skills, points, attempt_cfg) = match load_profile_config(true) {
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
        run_engine_loop(app, task_cancel, config, skills, points, attempt_cfg).await;
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
    let (config, skills, points, attempt_cfg) = load_profile_config(false)?;

    let sampler = DirectPixelSampler;
    simulate_rotation_with_sampler(&config, &skills, &points, &sampler, attempt_cfg)
}

#[tauri::command]
pub fn simulate_rotation_with_pixels(pixel_overrides: Vec<PixelOverride>) -> CommandResult<String> {
    let (config, skills, points, attempt_cfg) = load_profile_config(false)?;
    let sampler = OverridePixelSampler::new(pixel_overrides);
    simulate_rotation_with_sampler(&config, &skills, &points, &sampler, attempt_cfg)
}

#[tauri::command]
pub fn simulate_profile_rotation(content: String) -> CommandResult<String> {
    let profile = parse_profile_content(&content)?;
    let (config, skills, points, attempt_cfg) = simulation_inputs_from_profile(profile)?;

    let sampler = DirectPixelSampler;
    simulate_rotation_with_sampler(&config, &skills, &points, &sampler, attempt_cfg)
}

#[tauri::command]
pub fn simulate_profile_rotation_with_pixels(
    content: String,
    pixel_overrides: Vec<PixelOverride>,
) -> CommandResult<String> {
    let profile = parse_profile_content(&content)?;
    let (config, skills, points, attempt_cfg) = simulation_inputs_from_profile(profile)?;
    let sampler = OverridePixelSampler::new(pixel_overrides);
    simulate_rotation_with_sampler(&config, &skills, &points, &sampler, attempt_cfg)
}

#[tauri::command]
pub fn simulate_ipc_smoke_fixture() -> CommandResult<String> {
    let profile = smoke_fixture_profile();

    let mut direct_profile = profile.clone();
    if let Some(slot) = direct_profile
        .rotations
        .get_mut(0)
        .and_then(|rotation| rotation.phases.get_mut(0))
        .and_then(|phase| phase.skills.get_mut(0))
    {
        slot.condition_expr = None;
    }

    let (config, skills, points, attempt_cfg) = simulation_inputs_from_profile(direct_profile)?;
    let direct_sampler = DirectPixelSampler;
    let direct_json =
        simulate_rotation_with_sampler(&config, &skills, &points, &direct_sampler, attempt_cfg)?;

    let (config, skills, points, attempt_cfg) = simulation_inputs_from_profile(profile.clone())?;
    let pixel_sampler = OverridePixelSampler::new(smoke_fixture_pixel_overrides());
    let pixel_json =
        simulate_rotation_with_sampler(&config, &skills, &points, &pixel_sampler, attempt_cfg)?;

    let summary = IpcSmokeFixtureSummary {
        profile_id: profile.meta.profile_id,
        direct_events: event_count_from_simulation_json(&direct_json)?,
        pixel_events: event_count_from_simulation_json(&pixel_json)?,
    };

    serde_json::to_string_pretty(&summary)
        .map_err(AppError::from)
        .map_err(Into::into)
}

fn simulate_rotation_with_sampler(
    config: &CycleConfig,
    skills: &[Skill],
    points: &[Point],
    sampler: &dyn PixelSampler,
    attempt_cfg: SkillAttemptConfig,
) -> CommandResult<String> {
    let roi_provider = attempt_cfg
        .cast_bar_roi
        .clone()
        .map(ScreenCastBarRoiProvider::new);
    let mut executor = CycleExecutor::new(config, points, skills, sampler, attempt_cfg)
        .with_cast_bar_roi_provider(
            roi_provider
                .as_ref()
                .map(|provider| provider as &dyn CastBarRoiProvider),
        );

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
    let mut log_cursor = 0usize;

    for _tick in 0..max_ticks {
        let acted = executor.tick(&mut key_sender, &|| false, time_ms);

        for log in &executor.log[log_cursor..] {
            let skill = skills.iter().find(|skill| skill.id == log.skill_id);
            let cast_ms = skill.map(|skill| skill.cast.readbar_ms).unwrap_or(0) as u64;
            let cd_ms = skill.map(|skill| skill.cooldown_ms).unwrap_or(0) as u64;

            sim_events.push(serde_json::json!({
                "index": sim_events.len() + 1,
                "timeMs": log.ts_ms,
                "phase": log.phase_name,
                "event": log.event,
                "skillId": log.skill_id,
                "skillName": log.skill_name,
                "outcome": log.outcome,
                "castMs": cast_ms,
                "cdMs": cd_ms,
                "reason": log.reason,
            }));
        }
        log_cursor = executor.log.len();

        if acted {
            let gap = 50_u64;
            let cast_ms = skills
                .iter()
                .find(|skill| skill.id == executor.state.last_skill_id)
                .map(|skill| skill.cast.readbar_ms)
                .unwrap_or(0) as u64;
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
    use crate::models::cycle::{CyclePhase, SkillSlot};
    use crate::models::point::Point;
    use crate::models::skill::{CastConfig, ColorRGB, PixelSpec, SampleConfig};
    use crate::store::profile_store::default_profile;

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
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 100,
            max_cycles: 0,
            state_schema: None,
        };
        let mut runtime = RuntimeState::new();
        runtime.engine_started("default");
        runtime.mark_attempt_started("skill-1");
        runtime.mark_success("skill-1");

        let payload = runtime_payload(RuntimePayloadInput {
            runtime: &runtime,
            config: &config,
            skills: &[],
            total_executed: 1,
            cycle_count: 2,
            phase_index: 0,
            uptime_ms: 123,
            cast_bar_roi: Some(CastBarRoiStats {
                enabled: true,
                sample_count: 3,
                cache_hit_count: 2,
                failed_sample_count: 1,
                last_latency_us: 1200,
                avg_latency_us: 900,
                max_latency_us: 1500,
                last_changed_ratio: 0.25,
                last_border_match_ratio: 0.5,
                last_changed_from_baseline: true,
                last_border_visible: false,
                last_gone: false,
                last_error: String::new(),
            }),
        });

        assert!(payload.running);
        assert_eq!(payload.total_executed, 1);
        assert_eq!(payload.cycle_count, 2);
        assert_eq!(payload.uptime_ms, 123);
        assert_eq!(payload.skills.len(), 1);
        assert_eq!(payload.skills[0].skill_id, "skill-1");
        assert_eq!(payload.skills[0].state, "SUCCESS");
        assert_eq!(payload.skills[0].attempt_started, 1);
        assert_eq!(payload.skills[0].success, 1);
        let roi = payload.cast_bar_roi.unwrap();
        assert_eq!(roi.sample_count, 3);
        assert_eq!(roi.cache_hit_count, 2);
        assert_eq!(roi.avg_latency_us, 900);
    }

    fn test_skill(id: &str, key: &str, enabled: bool) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            enabled,
            trigger_key: key.into(),
            cast: CastConfig::default(),
            pixel: PixelSpec {
                monitor: "primary".into(),
                vx: 0,
                vy: 0,
                color: ColorRGB { r: 0, g: 0, b: 0 },
                tolerance: 0,
                sample: SampleConfig {
                    mode: "single".into(),
                    radius: 0,
                },
            },
            note: String::new(),
            game_id: 0,
            game_desc: String::new(),
            icon_url: String::new(),
            cooldown_ms: 0,
            radius: 0,
            shots_per_cycle: 1,
            ammo_stages: vec![],
        }
    }

    fn profile_with_slot(skill_id: &str) -> Profile {
        let mut profile = default_profile("default");
        profile.skills.skills = vec![test_skill(skill_id, "1", true)];
        profile.rotations[0].phases = vec![CyclePhase {
            name: "P1".into(),
            skills: vec![SkillSlot {
                skill_id: skill_id.into(),
                priority: 1,
                label: String::new(),
                condition_expr: None,
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }];
        profile
    }

    #[test]
    fn test_engine_profile_validation_rejects_empty_default() {
        let profile = default_profile("default");

        assert!(matches!(
            validate_engine_profile(&profile, false),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_engine_profile_validation_accepts_enabled_slot_with_key() {
        let profile = profile_with_slot("skill-1");

        assert!(validate_engine_profile(&profile, false).is_ok());
    }

    #[test]
    fn test_engine_profile_validation_rejects_disabled_execution_for_start() {
        let profile = profile_with_slot("skill-1");

        assert!(matches!(
            validate_engine_profile(&profile, true),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_engine_profile_validation_accepts_enabled_execution_for_start() {
        let mut profile = profile_with_slot("skill-1");
        profile.base.exec.enabled = true;

        assert!(validate_engine_profile(&profile, true).is_ok());
    }

    #[test]
    fn test_preflight_report_rejects_empty_default_profile() {
        let profile = default_profile("default");

        let report = preflight_report_from_profile(&profile, false);

        assert!(!report.ready);
        assert!(!report.exec_enabled);
        assert_eq!(report.executable_slot_count, 0);
        assert!(report.error.is_some());
    }

    #[test]
    fn test_preflight_report_accepts_enabled_executable_profile() {
        let mut profile = profile_with_slot("skill-1");
        profile.base.exec.enabled = true;

        let report = preflight_report_from_profile(&profile, false);

        assert!(report.ready);
        assert!(report.exec_enabled);
        assert_eq!(report.skill_count, 1);
        assert_eq!(report.executable_slot_count, 1);
        assert!(report.error.is_none());
    }

    #[test]
    fn test_preflight_report_rejects_running_engine() {
        let mut profile = profile_with_slot("skill-1");
        profile.base.exec.enabled = true;

        let report = preflight_report_from_profile(&profile, true);

        assert!(!report.ready);
        assert_eq!(report.error.as_deref(), Some("engine already running"));
    }

    #[test]
    fn test_attempt_config_uses_base_exec_values() {
        let mut profile = profile_with_slot("skill-1");
        profile.base.exec.default_skill_gap_ms = 77;
        profile.base.exec.poll_not_ready_ms = 88;
        profile.base.exec.max_retries = 2;
        profile.base.exec.retry_gap_ms = 33;
        profile.base.cast_bar.poll_interval_ms = 44;
        profile.base.cast_bar.max_wait_factor = 2.0;

        let cfg = attempt_config_from_base(&profile.base);

        assert_eq!(cfg.default_gap_ms, 77);
        assert_eq!(cfg.poll_not_ready_ms, 88);
        assert_eq!(cfg.max_retries, 2);
        assert_eq!(cfg.retry_gap_ms, 33);
        assert_eq!(cfg.complete_poll_ms, 44);
        assert_eq!(cfg.complete_max_wait_factor, 2.0);
    }

    #[test]
    fn test_attempt_config_enables_roi_when_mode_is_roi() {
        let mut profile = profile_with_slot("skill-1");
        profile.base.cast_bar.mode = "roi".into();
        profile.base.cast_bar.roi.enabled = false;
        profile.base.cast_bar.roi.width = 320;
        profile.base.cast_bar.roi.height = 28;

        let cfg = attempt_config_from_base(&profile.base);

        let roi = cfg.cast_bar_roi.unwrap();
        assert!(roi.enabled);
        assert_eq!(roi.width, 320);
        assert_eq!(roi.height, 28);
    }

    #[test]
    fn test_simulate_with_pixel_overrides_satisfies_point_condition() {
        let config = CycleConfig {
            name: "sim".into(),
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 1,
            state_schema: None,
            phases: vec![CyclePhase {
                name: "P1".into(),
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
                skills: vec![SkillSlot {
                    skill_id: "skill-1".into(),
                    priority: 1,
                    label: String::new(),
                    condition_expr: Some(serde_json::json!({
                        "type": "pixel_point",
                        "point_id": "point-1",
                        "tolerance": 0
                    })),
                    start_expr: None,
                    complete_expr: None,
                    override_cast_ms: None,
                    protected_release: false,
                    attempt_policy: None,
                    post_actions: vec![],
                }],
            }],
        };
        let skills = vec![test_skill("skill-1", "1", true)];
        let points = vec![Point {
            id: "point-1".into(),
            name: "point".into(),
            monitor: "primary".into(),
            vx: 10,
            vy: 20,
            color: ColorRGB { r: 1, g: 2, b: 3 },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
            captured_at: String::new(),
            note: String::new(),
        }];
        let sampler = OverridePixelSampler::new(vec![PixelOverride {
            monitor: "primary".into(),
            x: 10,
            y: 20,
            r: 1,
            g: 2,
            b: 3,
        }]);

        let json = simulate_rotation_with_sampler(
            &config,
            &skills,
            &points,
            &sampler,
            SkillAttemptConfig::default(),
        )
        .unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        let events = value["events"].as_array().unwrap();

        assert!(!events.is_empty());
        assert_eq!(events[0]["skillId"], "skill-1");
    }

    #[test]
    fn test_simulate_with_pixel_overrides_reports_condition_reason() {
        let config = CycleConfig {
            name: "sim".into(),
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 1,
            state_schema: None,
            phases: vec![CyclePhase {
                name: "P1".into(),
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
                skills: vec![SkillSlot {
                    skill_id: "skill-1".into(),
                    priority: 1,
                    label: String::new(),
                    condition_expr: Some(serde_json::json!({
                        "type": "pixel_point",
                        "point_id": "point-1",
                        "tolerance": 0
                    })),
                    start_expr: None,
                    complete_expr: None,
                    override_cast_ms: None,
                    protected_release: false,
                    attempt_policy: None,
                    post_actions: vec![],
                }],
            }],
        };
        let skills = vec![test_skill("skill-1", "1", true)];
        let points = vec![Point {
            id: "point-1".into(),
            name: "point".into(),
            monitor: "primary".into(),
            vx: 10,
            vy: 20,
            color: ColorRGB { r: 1, g: 2, b: 3 },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
            captured_at: String::new(),
            note: String::new(),
        }];
        let sampler = OverridePixelSampler::new(vec![PixelOverride {
            monitor: "primary".into(),
            x: 10,
            y: 20,
            r: 9,
            g: 9,
            b: 9,
        }]);

        let json = simulate_rotation_with_sampler(
            &config,
            &skills,
            &points,
            &sampler,
            SkillAttemptConfig::default(),
        )
        .unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        let events = value["events"].as_array().unwrap();

        assert!(!events.is_empty());
        assert_eq!(events[0]["event"], "skip");
        assert_eq!(events[0]["outcome"], "NOT_READY");
        assert!(
            events[0]["reason"]
                .as_str()
                .is_some_and(|reason| reason.starts_with("condition_false:"))
        );
    }

    #[test]
    fn test_simulate_profile_rotation_with_pixels_accepts_profile_content() {
        let mut profile = profile_with_slot("skill-1");
        profile.rotations[0].max_cycles = 1;
        let content = serde_json::to_string(&profile).unwrap();

        let json = simulate_profile_rotation_with_pixels(content, vec![]).unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        let events = value["events"].as_array().unwrap();

        assert!(!events.is_empty());
        assert_eq!(events[0]["skillId"], "skill-1");
    }

    #[test]
    fn test_simulate_profile_rotation_rejects_empty_profile_content() {
        let profile = default_profile("default");
        let content = serde_json::to_string(&profile).unwrap();

        assert!(simulate_profile_rotation_with_pixels(content, vec![]).is_err());
    }

    #[test]
    fn test_simulate_ipc_smoke_fixture_returns_event_counts() {
        let json = simulate_ipc_smoke_fixture().unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();

        assert_eq!(value["profile_id"], "ipc-smoke");
        assert!(
            value["direct_events"]
                .as_u64()
                .is_some_and(|count| count > 0)
        );
        assert!(
            value["pixel_events"]
                .as_u64()
                .is_some_and(|count| count > 0)
        );
    }
}
