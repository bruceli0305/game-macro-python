//! One-shot phase range runner used by the always-on-top debug panel.

use serde::{Deserialize, Serialize};
use tokio_util::sync::CancellationToken;

use crate::ast::evaluator::{CastBarRoiProvider, PixelSampler};
use crate::capture::capturer::CachedPixelSampler;
use crate::capture::cast_bar_roi::ScreenCastBarRoiProvider;
use crate::engine::cycle_executor::{CycleExecLogEntry, CycleExecutor};
use crate::engine::profile_config::EngineProfileInput;
use crate::engine::skill_attempt::{KeySender, SkillAttemptConfig};
use crate::error::{AppError, AppResult};
use crate::input::EnigoKeySender;
use crate::models::cycle::CycleConfig;
use crate::models::point::Point;
use crate::models::skill::Skill;

const MAX_DEBUG_TICKS: u32 = 2_000;
const MAX_DEBUG_ELAPSED_MS: u64 = 30_000;

#[derive(Debug, Clone, Deserialize)]
pub struct DebugRunRequest {
    pub start_phase_index: usize,
    pub end_phase_index: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct DebugRunStartedPayload {
    pub run_id: String,
    pub start_phase_index: usize,
    pub end_phase_index: usize,
    pub started_at_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DebugRunEventPayload {
    pub run_id: String,
    pub ts_ms: u64,
    pub phase_index: usize,
    pub phase_name: String,
    pub skill_id: String,
    pub skill_name: String,
    pub key: String,
    pub event: String,
    pub outcome: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DebugRunFinishedPayload {
    pub run_id: String,
    pub status: String,
    pub reason: String,
    pub elapsed_ms: u64,
    pub total_events: usize,
}

#[derive(Debug, Clone)]
pub enum DebugRunEvent {
    Event(DebugRunEventPayload),
    Finished(DebugRunFinishedPayload),
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DebugRunStop {
    Continue,
    Finished(String),
    Stopped,
    Failed(String),
}

pub(crate) fn validate_debug_phase_range(
    config: &CycleConfig,
    request: &DebugRunRequest,
) -> AppResult<()> {
    if request.start_phase_index > request.end_phase_index {
        return Err(AppError::Config(
            "debug start phase must be before or equal to end phase".into(),
        ));
    }
    if config.phases.is_empty() {
        return Err(AppError::Config("rotation has no phases".into()));
    }
    if request.start_phase_index >= config.phases.len()
        || request.end_phase_index >= config.phases.len()
    {
        return Err(AppError::Config(format!(
            "debug phase range {}..{} is out of bounds for {} phases",
            request.start_phase_index,
            request.end_phase_index,
            config.phases.len()
        )));
    }
    Ok(())
}

pub(crate) async fn run_debug_once_with_real_input(
    run_id: String,
    input: EngineProfileInput,
    request: DebugRunRequest,
    cancel: CancellationToken,
    mut emit: impl FnMut(DebugRunEvent) + Send + 'static,
) -> AppResult<()> {
    validate_debug_phase_range(&input.config, &request)?;

    let sampler = CachedPixelSampler::new();
    let roi_provider = input
        .attempt_cfg
        .cast_bar_roi
        .clone()
        .map(|cfg| ScreenCastBarRoiProvider::with_shared_sampler(cfg, &sampler));
    let mut key_sender = EnigoKeySender::new().map_err(AppError::Input)?;

    run_debug_once_loop(
        &run_id,
        &input.config,
        &input.skills,
        &input.points,
        &sampler,
        roi_provider
            .as_ref()
            .map(|provider| provider as &dyn CastBarRoiProvider),
        input.attempt_cfg,
        &request,
        &cancel,
        &mut key_sender,
        true,
        &mut emit,
    )
    .await;

    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub(crate) async fn run_debug_once_loop(
    run_id: &str,
    config: &CycleConfig,
    skills: &[Skill],
    points: &[Point],
    sampler: &dyn PixelSampler,
    cast_bar_roi: Option<&dyn CastBarRoiProvider>,
    attempt_cfg: SkillAttemptConfig,
    request: &DebugRunRequest,
    cancel: &CancellationToken,
    key_sender: &mut dyn KeySender,
    sleep_between_ticks: bool,
    emit: &mut (dyn FnMut(DebugRunEvent) + Send),
) {
    let mut executor = CycleExecutor::new(config, points, skills, sampler, attempt_cfg)
        .with_cast_bar_roi_provider(cast_bar_roi);
    executor.state.phase_index = request.start_phase_index;
    executor.runtime.engine_started(&config.name);

    let mut tick_count = 0_u32;
    let mut emitted_events = 0_usize;
    let poll_ms = u64::from(config.poll_interval_ms.max(1));
    let mut now_ms = 0_u64;

    loop {
        let stopped = debug_stop_reason(
            &executor,
            request,
            cancel,
            tick_count,
            now_ms,
            &executor.log,
        );
        match stopped {
            DebugRunStop::Continue => {}
            DebugRunStop::Finished(reason) => {
                emit(DebugRunEvent::Finished(DebugRunFinishedPayload {
                    run_id: run_id.into(),
                    status: "completed".into(),
                    reason,
                    elapsed_ms: now_ms,
                    total_events: emitted_events,
                }));
                break;
            }
            DebugRunStop::Stopped => {
                emit(DebugRunEvent::Finished(DebugRunFinishedPayload {
                    run_id: run_id.into(),
                    status: "stopped".into(),
                    reason: "cancelled".into(),
                    elapsed_ms: now_ms,
                    total_events: emitted_events,
                }));
                break;
            }
            DebugRunStop::Failed(reason) => {
                emit(DebugRunEvent::Finished(DebugRunFinishedPayload {
                    run_id: run_id.into(),
                    status: "failed".into(),
                    reason,
                    elapsed_ms: now_ms,
                    total_events: emitted_events,
                }));
                break;
            }
        }

        executor.tick(key_sender, &|| cancel.is_cancelled(), now_ms);

        for event in drain_debug_events(run_id, &mut executor, skills) {
            emitted_events += 1;
            emit(DebugRunEvent::Event(event));
        }

        tick_count = tick_count.saturating_add(1);
        now_ms = now_ms.saturating_add(poll_ms);

        if sleep_between_ticks {
            tokio::select! {
                () = cancel.cancelled() => {}
                () = tokio::time::sleep(std::time::Duration::from_millis(poll_ms)) => {}
            }
        }
    }
}

fn debug_stop_reason(
    executor: &CycleExecutor<'_>,
    request: &DebugRunRequest,
    cancel: &CancellationToken,
    tick_count: u32,
    now_ms: u64,
    logs: &[CycleExecLogEntry],
) -> DebugRunStop {
    if cancel.is_cancelled() {
        return DebugRunStop::Stopped;
    }
    if tick_count >= MAX_DEBUG_TICKS || now_ms >= MAX_DEBUG_ELAPSED_MS {
        return DebugRunStop::Failed("debug_run_timeout".into());
    }
    if executor.state.cycle_count > 0 || executor.state.phase_index > request.end_phase_index {
        return DebugRunStop::Finished("range_completed".into());
    }
    if logs.iter().any(|log| {
        log.phase_index >= request.end_phase_index
            && (log.event == "phase_transition" || log.event == "phase_complete")
    }) {
        return DebugRunStop::Finished("range_completed".into());
    }
    DebugRunStop::Continue
}

fn drain_debug_events(
    run_id: &str,
    executor: &mut CycleExecutor<'_>,
    skills: &[Skill],
) -> Vec<DebugRunEventPayload> {
    let logs = std::mem::take(&mut executor.log);
    logs.into_iter()
        .map(|log| {
            let key = skills
                .iter()
                .find(|skill| skill.id == log.skill_id)
                .map(|skill| skill.trigger_key.clone())
                .unwrap_or_default();
            DebugRunEventPayload {
                run_id: run_id.into(),
                ts_ms: log.ts_ms,
                phase_index: log.phase_index,
                phase_name: log.phase_name,
                skill_id: log.skill_id,
                skill_name: log.skill_name,
                key,
                event: log.event,
                outcome: normalize_outcome(&log.outcome),
                reason: log.reason,
            }
        })
        .collect()
}

fn normalize_outcome(outcome: &str) -> String {
    match outcome {
        "Success" => "SUCCESS",
        "Failed" | "Error" => "FAILED",
        "SkippedNotReady" => "NOT_READY",
        "SkippedDisabled" | "SkippedLockBusy" | "ALREADY_FIRED" => "SKIP",
        "Stopped" => "STOPPED",
        "Applied" | "NONE_READY" => "INFO",
        value => value,
    }
    .into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::simulation::OverridePixelSampler;
    use crate::models::cycle::{CyclePhase, SkillSlot, SkillSlotRole};
    use crate::models::skill::{CastConfig, PixelSpec};

    #[derive(Default)]
    struct DummyKeySender {
        keys: Vec<String>,
    }

    impl KeySender for DummyKeySender {
        fn send_key(&mut self, key: &str) -> bool {
            self.keys.push(key.into());
            true
        }
    }

    fn skill(id: &str, key: &str) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            enabled: true,
            trigger_key: key.into(),
            cast: CastConfig::default(),
            pixel: PixelSpec {
                monitor: String::new(),
                vx: 0,
                vy: 0,
                color: Default::default(),
                tolerance: 0,
                sample: Default::default(),
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

    fn phase(name: &str, skill_id: &str) -> CyclePhase {
        CyclePhase {
            name: name.into(),
            skills: vec![SkillSlot {
                skill_id: skill_id.into(),
                priority: 1,
                label: String::new(),
                slot_role: SkillSlotRole::Mandatory,
                readiness_expr: None,
                readiness_policy: Default::default(),
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
        }
    }

    fn config() -> CycleConfig {
        CycleConfig {
            name: "debug".into(),
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 1,
            state_schema: None,
            phases: vec![phase("P1", "skill-1"), phase("P2", "skill-2")],
        }
    }

    #[test]
    fn validate_debug_phase_range_rejects_invalid_order() {
        let config = config();
        let request = DebugRunRequest {
            start_phase_index: 1,
            end_phase_index: 0,
        };

        assert!(validate_debug_phase_range(&config, &request).is_err());
    }

    #[tokio::test]
    async fn single_phase_run_stops_at_selected_end_phase() {
        let config = config();
        let skills = vec![skill("skill-1", "1"), skill("skill-2", "2")];
        let points = vec![];
        let sampler = OverridePixelSampler::new(vec![]);
        let request = DebugRunRequest {
            start_phase_index: 0,
            end_phase_index: 0,
        };
        let cancel = CancellationToken::new();
        let mut key_sender = DummyKeySender::default();
        let mut events = Vec::new();

        run_debug_once_loop(
            "run-1",
            &config,
            &skills,
            &points,
            &sampler,
            None,
            SkillAttemptConfig::default(),
            &request,
            &cancel,
            &mut key_sender,
            false,
            &mut |event| events.push(event),
        )
        .await;

        assert_eq!(key_sender.keys, vec!["1"]);
        assert!(matches!(
            events.last(),
            Some(DebugRunEvent::Finished(payload))
                if payload.status == "completed" && payload.reason == "range_completed"
        ));
    }

    #[tokio::test]
    async fn phase_range_run_reaches_end_phase_once() {
        let config = config();
        let skills = vec![skill("skill-1", "1"), skill("skill-2", "2")];
        let points = vec![];
        let sampler = OverridePixelSampler::new(vec![]);
        let request = DebugRunRequest {
            start_phase_index: 0,
            end_phase_index: 1,
        };
        let cancel = CancellationToken::new();
        let mut key_sender = DummyKeySender::default();
        let mut events = Vec::new();

        run_debug_once_loop(
            "run-1",
            &config,
            &skills,
            &points,
            &sampler,
            None,
            SkillAttemptConfig::default(),
            &request,
            &cancel,
            &mut key_sender,
            false,
            &mut |event| events.push(event),
        )
        .await;

        assert_eq!(key_sender.keys, vec!["1", "2"]);
        assert!(events.iter().any(|event| matches!(
            event,
            DebugRunEvent::Event(payload)
                if payload.phase_index == 1
                    && payload.skill_id == "skill-2"
                    && payload.key == "2"
                    && payload.outcome == "SUCCESS"
        )));
    }
}
