//! Execution state and event/log helpers for `CycleExecutor`.

use std::collections::{HashMap, HashSet};

use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::skill_attempt::AttemptEvent;
use crate::models::cycle::SkillSlot;

#[derive(Debug, Clone, Default)]
pub struct CycleExecState {
    pub phase_index: usize,
    pub next_ready_ms: u64,
    pub cycle_count: u32,
    pub fired_in_phase: HashSet<String>,
    pub fired_in_cycle: HashSet<String>,
    pub fired_count_in_cycle: HashMap<String, u32>,
    pub skill_ready_at_ms: HashMap<String, u64>,
    pub observer_lane_next_check_ms: HashMap<String, u64>,
    pub assist_lane_next_check_ms: HashMap<String, u64>,
    pub total_executed: u32,
    pub last_skill_id: String,
    pub last_outcome: String,
    pub phase_entry_applied: bool,
}

#[derive(Debug, Clone)]
pub struct CycleExecLogEntry {
    pub ts_ms: u64,
    pub phase_index: usize,
    pub phase_name: String,
    pub event: String,
    pub skill_id: String,
    pub skill_name: String,
    pub outcome: String,
    pub reason: String,
}

pub(crate) struct CycleLogEvent<'a> {
    pub(crate) ts_ms: u64,
    pub(crate) phase_index: usize,
    pub(crate) phase_name: &'a str,
    pub(crate) event: &'a str,
    pub(crate) skill_id: &'a str,
    pub(crate) outcome: &'a str,
    pub(crate) reason: &'a str,
}

impl<'a> CycleExecutor<'a> {
    pub(super) fn apply_attempt_event(&mut self, event: AttemptEvent) {
        match event {
            AttemptEvent::AttemptStarted { skill_id } => {
                self.runtime.mark_attempt_started(&skill_id);
            }
            AttemptEvent::KeySentOk { skill_id } => {
                self.runtime.mark_key_sent_ok(&skill_id);
            }
            AttemptEvent::CastStarted { skill_id } => {
                self.runtime.mark_cast_started(&skill_id);
            }
            AttemptEvent::CompleteWaitStarted { skill_id } => {
                self.runtime.mark_complete_wait_started(&skill_id);
            }
            AttemptEvent::Succeeded { skill_id } => {
                self.runtime.mark_success(&skill_id);
            }
            AttemptEvent::Failed { skill_id, reason } => {
                self.runtime.mark_fail(&skill_id, &reason);
            }
            AttemptEvent::Stopped { skill_id } => {
                self.runtime.mark_stopped(&skill_id);
            }
        }
    }

    pub(super) fn log_event(&mut self, event: CycleLogEvent<'_>) {
        let skill_name = self
            .skills
            .iter()
            .find(|s| s.id.as_str() == event.skill_id)
            .map(|s| s.name.as_str())
            .unwrap_or("");
        self.log.push(CycleExecLogEntry {
            ts_ms: event.ts_ms,
            phase_index: event.phase_index,
            phase_name: event.phase_name.into(),
            event: event.event.into(),
            skill_id: event.skill_id.into(),
            skill_name: skill_name.into(),
            outcome: event.outcome.into(),
            reason: event.reason.into(),
        });
    }

    /// Returns skill slots sorted by priority for a phase.
    pub fn sorted_slots_for_phase(&self, phase_idx: usize) -> Vec<&SkillSlot> {
        let mut slots: Vec<_> = self
            .config
            .phases
            .get(phase_idx)
            .map(|p| p.skills.iter().collect())
            .unwrap_or_default();
        slots.sort_by_key(|s| s.priority);
        slots
    }
}
