//! Runtime payload mapping for engine event emission.

use serde::Serialize;

use crate::ast::evaluator::CastBarRoiStats;
use crate::engine::runtime_state::{AttemptStage, RuntimeState};
use crate::models::cycle::CycleConfig;
use crate::models::skill::Skill;

#[derive(Debug, Clone, Serialize)]
pub(crate) struct EngineRuntimePayload {
    pub running: bool,
    pub paused: bool,
    pub preset_id: String,
    pub stop_reason: String,
    pub total_executed: u32,
    pub cycle_count: u32,
    pub phase_index: usize,
    pub phase_name: String,
    pub uptime_ms: u64,
    pub cast_bar_roi: Option<CastBarRoiRuntimePayload>,
    pub skills: Vec<SkillRuntimePayload>,
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct CastBarRoiRuntimePayload {
    pub(crate) enabled: bool,
    pub(crate) sample_count: u64,
    pub(crate) cache_hit_count: u64,
    pub(crate) failed_sample_count: u64,
    pub(crate) last_latency_us: u64,
    pub(crate) avg_latency_us: u64,
    pub(crate) max_latency_us: u64,
    pub(crate) last_changed_ratio: f64,
    pub(crate) last_border_match_ratio: f64,
    pub(crate) last_changed_from_baseline: bool,
    pub(crate) last_border_visible: bool,
    pub(crate) last_gone: bool,
    pub(crate) last_error: String,
}

pub(crate) struct RuntimePayloadInput<'a> {
    pub runtime: &'a RuntimeState,
    pub config: &'a CycleConfig,
    pub skills: &'a [Skill],
    pub total_executed: u32,
    pub cycle_count: u32,
    pub phase_index: usize,
    pub uptime_ms: u64,
    pub cast_bar_roi: Option<CastBarRoiStats>,
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct SkillRuntimePayload {
    pub(crate) skill_id: String,
    pub(crate) skill_name: String,
    pub(crate) state: String,
    pub(crate) node_exec: u32,
    pub(crate) ready_false: u32,
    pub(crate) skipped_disabled: u32,
    pub(crate) skipped_lock_busy: u32,
    pub(crate) attempt_started: u32,
    pub(crate) key_sent_ok: u32,
    pub(crate) cast_started: u32,
    pub(crate) success: u32,
    pub(crate) fail: u32,
}

pub(crate) fn runtime_payload(input: RuntimePayloadInput<'_>) -> EngineRuntimePayload {
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
