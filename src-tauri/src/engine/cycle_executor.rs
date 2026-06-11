//! Phase and priority cycle executor.
//!
//! Execution model:
//! 1. Keep the active phase index and fired skill sets.
//! 2. On each tick, scan the active phase by priority.
//! 3. Start the first ready skill attempt.
//! 4. Advance pending attempts across later ticks without blocking.
//! 5. Advance or reset phases after attempts finish.

use crate::ast::evaluator::{CastBarRoiProvider, PixelSampler};
use crate::ast::nodes::Expr;
use crate::engine::runtime_state::RuntimeState;
use crate::engine::skill_attempt::{AttemptEvent, KeySender, SkillAttemptConfig};
// Re-exported for tests (CompletePolicy is used in test fixtures).
#[allow(unused_imports)]
pub(crate) use crate::engine::skill_attempt::CompletePolicy;
use crate::models::cycle::{CycleConfig, SkillSlot};
use crate::models::point::Point;
use crate::models::skill::Skill;
use std::collections::{HashMap, HashSet};

// ---------------------------------------------------------------------------
// Cycle execution state.
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// CycleExecLogEntry
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Cycle executor.
// ---------------------------------------------------------------------------

pub struct CycleExecutor<'a> {
    pub config: &'a CycleConfig,
    pub points: &'a [Point],
    pub skills: &'a [Skill],
    pub sampler: &'a dyn PixelSampler,
    pub cast_bar_roi: Option<&'a dyn CastBarRoiProvider>,
    pub attempt_cfg: SkillAttemptConfig,
    pub state: CycleExecState,
    pub runtime: RuntimeState,
    pub log: Vec<CycleExecLogEntry>,

    // Owned by attempt_tracker / phase_manager impl blocks.
    pub(crate) pending_attempt: Option<PendingAttempt>,
    pub(crate) suspended_main_attempt: Option<PendingAttempt>,
    pub(crate) slot_expr_cache: HashMap<SlotExprKey, CompiledSlotExprs>,
    pub(crate) observer_action_expr_cache: HashMap<ObserverActionExprKey, Option<Expr>>,
    pub(crate) transition_rule_expr_cache: Vec<Vec<Option<Expr>>>,
}

// Re-export items moved to sibling modules so `super::*` in tests still sees them.
pub(crate) use crate::engine::phase_manager::phase_reacquire_score;
pub(crate) use crate::engine::runtime_config::{
    AttemptContext, CompiledSlotExprs, ObserverActionExprKey, PendingAttempt, SlotExprKey,
    build_observer_action_expr_cache, build_slot_expr_cache, build_transition_rule_expr_cache,
};

impl<'a> CycleExecutor<'a> {
    pub fn new(
        config: &'a CycleConfig,
        points: &'a [Point],
        skills: &'a [Skill],
        sampler: &'a dyn PixelSampler,
        attempt_cfg: SkillAttemptConfig,
    ) -> Self {
        let slot_expr_cache = build_slot_expr_cache(config);
        let observer_action_expr_cache = build_observer_action_expr_cache(config);
        let transition_rule_expr_cache = build_transition_rule_expr_cache(config);

        let mut runtime = RuntimeState::new();
        if let Some(schema) = &config.state_schema {
            for marker in &schema.markers {
                runtime.set_marker(&marker.id, &marker.initial_value);
            }
            for counter in &schema.counters {
                runtime.set_counter(&counter.id, counter.initial_value);
            }
        }

        Self {
            config,
            points,
            skills,
            sampler,
            cast_bar_roi: None,
            attempt_cfg,
            state: CycleExecState::default(),
            runtime,
            log: Vec::new(),
            pending_attempt: None,
            suspended_main_attempt: None,
            slot_expr_cache,
            observer_action_expr_cache,
            transition_rule_expr_cache,
        }
    }

    pub fn with_cast_bar_roi_provider(
        mut self,
        provider: Option<&'a dyn CastBarRoiProvider>,
    ) -> Self {
        self.cast_bar_roi = provider;
        self
    }

    /// Select the best matching phase from the current screen state.
    ///
    /// This is intended for engine startup/resume after the player moved,
    /// handled mechanics, or manually released skills. Explicit transition
    /// rules win first; otherwise the first completion slot's complete signal
    /// is treated as a phase anchor.
    pub fn reacquire_phase_from_current_frame(&mut self, now_ms: u64) -> Option<usize> {
        self.runtime.set_now_ms(now_ms);
        self.sampler.begin_tick(now_ms);
        if let Some(provider) = self.cast_bar_roi {
            provider.begin_tick(now_ms);
        }

        if self.config.phases.is_empty() {
            return None;
        }

        for (phase_idx, phase) in self.config.phases.iter().enumerate() {
            for (rule_index, rule) in phase.transition_rules.iter().enumerate() {
                if !self.transition_rule_matches(phase_idx, rule_index) {
                    continue;
                }
                let Some(target_index) = self.find_phase_index(&rule.target_phase) else {
                    continue;
                };
                let label = rule.label.trim();
                let rule_name = if label.is_empty() { "unnamed" } else { label };
                self.apply_reacquired_phase(
                    target_index,
                    now_ms,
                    &format!("transition_rule:{rule_name}->{}", rule.target_phase.trim()),
                );
                return Some(target_index);
            }
        }

        let best_phase = self
            .config
            .phases
            .iter()
            .enumerate()
            .filter(|(phase_idx, phase)| self.phase_anchor_matches(*phase_idx, phase))
            .max_by_key(|(phase_idx, phase)| phase_reacquire_score(*phase_idx, phase))
            .map(|(phase_idx, _)| phase_idx);

        if let Some(phase_idx) = best_phase {
            let phase_name = self.config.phases[phase_idx].name.trim();
            self.apply_reacquired_phase(phase_idx, now_ms, &format!("phase_anchor:{phase_name}"));
        }

        best_phase
    }

    /// Advance the cycle executor by one scheduler tick.
    pub fn tick(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
    ) -> bool {
        self.runtime.set_now_ms(now_ms);
        self.sampler.begin_tick(now_ms);
        if let Some(provider) = self.cast_bar_roi {
            provider.begin_tick(now_ms);
        }

        if stopped() {
            if let Some(pending) = self.pending_attempt.take() {
                self.apply_attempt_event(AttemptEvent::Stopped {
                    skill_id: pending.skill_id,
                });
            }
            if let Some(pending) = self.suspended_main_attempt.take() {
                self.apply_attempt_event(AttemptEvent::Stopped {
                    skill_id: pending.skill_id,
                });
            }
            return false;
        }

        self.try_observer_lanes(now_ms);

        if let Some(pending) = self.pending_attempt.take() {
            if matches!(pending.context, AttemptContext::Main { .. })
                && !pending.protected_release
                && self.suspended_main_attempt.is_none()
                && self.try_assist_lanes(key_sender, stopped, now_ms, Some(pending.stage))
            {
                if self.pending_attempt.is_some() {
                    self.suspended_main_attempt = Some(pending);
                } else {
                    self.pending_attempt = Some(pending);
                }
                return true;
            }
            return self.advance_pending_attempt(key_sender, stopped, now_ms, pending);
        }

        if now_ms < self.state.next_ready_ms {
            return false;
        }

        let phases = &self.config.phases;
        if phases.is_empty() {
            return false;
        }

        if self.state.phase_index >= phases.len() {
            self.on_cycle_reset();
        }

        let phase_idx = self.state.phase_index;
        if phase_idx >= phases.len() {
            return false;
        }

        let phase = &phases[phase_idx];
        self.enter_phase_if_needed(phase_idx, phase, now_ms);
        let mut sorted_slots: Vec<(usize, &SkillSlot)> = phase.skills.iter().enumerate().collect();
        sorted_slots.sort_by_key(|(_, slot)| slot.priority);

        for (slot_index, slot) in sorted_slots {
            let sid = slot.skill_id.trim();
            if sid.is_empty() {
                continue;
            }

            if self.state.fired_in_phase.contains(sid)
                && phase.complete_when != "always"
                && !self.slot_can_fire_more_this_cycle(sid)
            {
                self.log_event(CycleLogEvent {
                    ts_ms: now_ms,
                    phase_index: phase_idx,
                    phase_name: &phase.name,
                    event: "skip",
                    skill_id: sid,
                    outcome: "ALREADY_FIRED",
                    reason: "already_fired_this_phase",
                });
                continue;
            }

            self.runtime.mark_node_exec(sid);

            let (ready, cond_reason) = self.check_skill_ready_at(
                slot,
                SlotExprKey::Phase {
                    phase_index: phase_idx,
                    slot_index,
                },
                now_ms,
            );
            if !ready {
                self.runtime.mark_ready_false(sid);
                self.log_event(CycleLogEvent {
                    ts_ms: now_ms,
                    phase_index: phase_idx,
                    phase_name: &phase.name,
                    event: "skip",
                    skill_id: sid,
                    outcome: "NOT_READY",
                    reason: &cond_reason,
                });
                continue;
            }

            if let Some(execution) = self.begin_skill_attempt(
                key_sender,
                slot,
                stopped,
                now_ms,
                AttemptContext::Main {
                    phase_index: phase_idx,
                },
                SlotExprKey::Phase {
                    phase_index: phase_idx,
                    slot_index,
                },
            ) {
                self.finish_skill_attempt(
                    phase_idx,
                    phase,
                    &slot.post_actions,
                    sid,
                    execution,
                    now_ms,
                );
            }

            return true;
        }

        if phase.complete_when == "none_ready" && self.is_phase_complete(phase_idx, phase) {
            self.log_event(CycleLogEvent {
                ts_ms: now_ms,
                phase_index: phase_idx,
                phase_name: &phase.name,
                event: "phase_complete",
                skill_id: "",
                outcome: "NONE_READY",
                reason: "all_slots_fired_or_not_ready",
            });
            self.on_phase_complete(phase_idx, phase, now_ms);
            if self.state.phase_index >= self.config.phases.len() {
                self.on_cycle_reset();
            }
            return true;
        }

        self.try_assist_lanes(key_sender, stopped, now_ms, None)
    }

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

// ===========================================================================
// Tests.
// ===========================================================================

#[cfg(test)]
#[path = "cycle_executor_tests.rs"]
mod tests;
