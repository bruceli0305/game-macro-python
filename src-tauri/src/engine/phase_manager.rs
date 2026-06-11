//! Phase management for CycleExecutor.
//!
//! Handles phase entry, completion detection, transition resolution,
//! reacquisition from frame, and cycle reset logic.

use crate::engine::cycle_executor::{CycleExecutor, CycleLogEvent};
use crate::engine::runtime_config::SlotExprKey;
use crate::models::cycle::{
    CyclePhase, PhaseFallbackTransition, RuntimeAction, SkillSlot, SkillSlotRole,
};

impl<'a> CycleExecutor<'a> {
    // ------------------------------------------------------------------
    // Phase entry.
    // ------------------------------------------------------------------

    pub(super) fn enter_phase_if_needed(
        &mut self,
        phase_idx: usize,
        phase: &CyclePhase,
        now_ms: u64,
    ) {
        if self.state.phase_entry_applied {
            return;
        }
        self.state.phase_entry_applied = true;
        self.reset_phase_entry_counters();
        self.apply_runtime_actions(&phase.entry_actions, now_ms, phase_idx, &phase.name, "");
    }

    // ------------------------------------------------------------------
    // Runtime action application (shared across phase entry, post-actions,
    // and observer lanes).
    // ------------------------------------------------------------------

    pub(super) fn apply_runtime_actions(
        &mut self,
        actions: &[RuntimeAction],
        now_ms: u64,
        phase_idx: usize,
        phase_name: &str,
        skill_id: &str,
    ) {
        for action in actions {
            let reason = match action {
                RuntimeAction::SetMarker { marker_id, value } => {
                    self.runtime.set_marker(marker_id, value);
                    format!("set_marker:{marker_id}={value}")
                }
                RuntimeAction::ClearMarker { marker_id } => {
                    self.runtime.clear_marker(marker_id);
                    format!("clear_marker:{marker_id}")
                }
                RuntimeAction::RecordTimer { timer_id } => {
                    self.runtime.record_timer(timer_id, now_ms);
                    format!("record_timer:{timer_id}")
                }
                RuntimeAction::ResetTimer { timer_id } => {
                    self.runtime.reset_timer(timer_id);
                    format!("reset_timer:{timer_id}")
                }
                RuntimeAction::IncrementCounter { counter_id, by } => {
                    self.runtime.increment_counter(counter_id, *by);
                    format!("increment_counter:{counter_id}+={by}")
                }
                RuntimeAction::SetCounter { counter_id, value } => {
                    self.runtime.set_counter(counter_id, *value);
                    format!("set_counter:{counter_id}={value}")
                }
                RuntimeAction::ResetCounter { counter_id } => {
                    self.reset_counter_to_initial(counter_id);
                    format!("reset_counter:{counter_id}")
                }
            };
            self.log_event(CycleLogEvent {
                ts_ms: now_ms,
                phase_index: phase_idx,
                phase_name,
                event: "runtime_action",
                skill_id,
                outcome: "Applied",
                reason: &reason,
            });
        }
    }

    // ------------------------------------------------------------------
    // Phase completion detection.
    // ------------------------------------------------------------------

    pub(super) fn is_phase_complete(&self, phase_idx: usize, phase: &CyclePhase) -> bool {
        let completion_slots = phase_completion_slot_indices(phase);
        match phase.complete_when.as_str() {
            "always" => true,
            "any_fired" => completion_slots.iter().any(|(_, slot)| {
                let sid = slot.skill_id.trim();
                !sid.is_empty() && self.state.fired_in_phase.contains(sid)
            }),
            "none_ready" => completion_slots.iter().all(|(slot_index, slot)| {
                let sid = slot.skill_id.trim();
                sid.is_empty()
                    || self.state.fired_in_phase.contains(sid)
                    || !self
                        .check_skill_ready_at(
                            slot,
                            SlotExprKey::Phase {
                                phase_index: phase_idx,
                                slot_index: *slot_index,
                            },
                            self.state.next_ready_ms,
                        )
                        .0
            }),
            _ => completion_slots.iter().all(|(_, slot)| {
                let skill_id = slot.skill_id.trim();
                skill_id.is_empty() || self.slot_shots_complete_this_cycle(skill_id)
            }),
        }
    }

    // ------------------------------------------------------------------
    // Phase transition.
    // ------------------------------------------------------------------

    pub(super) fn on_phase_complete(&mut self, phase_idx: usize, phase: &CyclePhase, now_ms: u64) {
        let (next_phase_index, reason) = self.resolve_phase_transition(phase_idx, phase);
        self.log_event(CycleLogEvent {
            ts_ms: now_ms,
            phase_index: phase_idx,
            phase_name: &phase.name,
            event: "phase_transition",
            skill_id: "",
            outcome: "Applied",
            reason: &reason,
        });
        self.state.phase_index = next_phase_index;
        self.state.fired_in_phase.clear();
        self.state.phase_entry_applied = false;
    }

    pub(super) fn resolve_phase_transition(
        &self,
        phase_idx: usize,
        phase: &CyclePhase,
    ) -> (usize, String) {
        for (rule_index, rule) in phase.transition_rules.iter().enumerate() {
            if self.transition_rule_matches(phase_idx, rule_index) {
                if let Some(target_index) = self.find_phase_index(&rule.target_phase) {
                    let label = rule.label.trim();
                    let rule_name = if label.is_empty() { "unnamed" } else { label };
                    return (
                        target_index,
                        format!("rule:{rule_name}->{}", rule.target_phase.trim()),
                    );
                }
                return (
                    phase_idx.saturating_add(1),
                    format!("rule_target_missing:{}", rule.target_phase.trim()),
                );
            }
        }

        match phase.fallback_transition.as_ref() {
            Some(PhaseFallbackTransition::Stay) => (phase_idx, "fallback:stay".into()),
            Some(PhaseFallbackTransition::Next) | None => {
                (phase_idx.saturating_add(1), "fallback:next".into())
            }
            Some(PhaseFallbackTransition::Phase { target_phase }) => self
                .find_phase_index(target_phase)
                .map(|target_index| {
                    (
                        target_index,
                        format!("fallback:phase->{}", target_phase.trim()),
                    )
                })
                .unwrap_or_else(|| {
                    (
                        phase_idx.saturating_add(1),
                        format!("fallback_target_missing:{}", target_phase.trim()),
                    )
                }),
        }
    }

    pub(super) fn transition_rule_matches(&self, phase_idx: usize, rule_index: usize) -> bool {
        self.transition_rule_expr_cache
            .get(phase_idx)
            .and_then(|rules| rules.get(rule_index))
            .and_then(Option::as_ref)
            .is_some_and(|expr| self.evaluate_expr(expr))
    }

    /// Check whether the highest-priority completion slot's `complete_expr`
    /// evaluates to true for reacquisition anchoring.
    pub(super) fn phase_anchor_matches(&self, phase_idx: usize, phase: &CyclePhase) -> bool {
        phase_completion_slot_indices(phase)
            .into_iter()
            .filter(|(_, slot)| !slot.skill_id.trim().is_empty())
            .min_by_key(|(_, slot)| slot.priority)
            .and_then(|(slot_index, _)| {
                self.slot_expr_cache
                    .get(&SlotExprKey::Phase {
                        phase_index: phase_idx,
                        slot_index,
                    })
                    .and_then(|exprs| exprs.complete_expr.as_ref())
            })
            .is_some_and(|expr| self.evaluate_expr(expr))
    }

    pub(super) fn find_phase_index(&self, target_phase: &str) -> Option<usize> {
        let target_phase = target_phase.trim();
        if target_phase.is_empty() {
            return None;
        }
        self.config
            .phases
            .iter()
            .position(|phase| phase.name.trim() == target_phase)
    }

    // ------------------------------------------------------------------
    // Phase reacquisition (frame-driven).
    // ------------------------------------------------------------------

    pub(super) fn apply_reacquired_phase(&mut self, phase_idx: usize, now_ms: u64, reason: &str) {
        let phase_name = self
            .config
            .phases
            .get(phase_idx)
            .map(|phase| phase.name.as_str())
            .unwrap_or("");
        self.state.phase_index = phase_idx;
        self.state.next_ready_ms = now_ms;
        self.state.fired_in_phase.clear();
        self.state.phase_entry_applied = false;
        self.pending_attempt = None;
        self.suspended_main_attempt = None;
        self.log_event(CycleLogEvent {
            ts_ms: now_ms,
            phase_index: phase_idx,
            phase_name,
            event: "phase_reacquire",
            skill_id: "",
            outcome: "Applied",
            reason,
        });
    }

    // ------------------------------------------------------------------
    // Cycle reset.
    // ------------------------------------------------------------------

    pub(super) fn on_cycle_reset(&mut self) {
        self.state.cycle_count += 1;
        self.state.phase_index = 0;
        self.state.fired_in_phase.clear();
        self.state.fired_in_cycle.clear();
        self.state.fired_count_in_cycle.clear();
        self.state.phase_entry_applied = false;
        if let Some(schema) = &self.config.state_schema {
            for timer in &schema.timers {
                if timer.reset_on_cycle_start {
                    self.runtime.reset_timer(&timer.id);
                }
            }
            for counter in &schema.counters {
                if counter.reset_on_cycle_start {
                    self.runtime.set_counter(&counter.id, counter.initial_value);
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // Counter helpers.
    // ------------------------------------------------------------------

    fn reset_phase_entry_counters(&mut self) {
        let Some(schema) = &self.config.state_schema else {
            return;
        };
        for counter in &schema.counters {
            if counter.reset_on_phase_entry {
                self.runtime.set_counter(&counter.id, counter.initial_value);
            }
        }
    }

    fn reset_counter_to_initial(&mut self, counter_id: &str) {
        let counter_id = counter_id.trim();
        if counter_id.is_empty() {
            return;
        }
        let initial_value = self
            .config
            .state_schema
            .as_ref()
            .and_then(|schema| {
                schema
                    .counters
                    .iter()
                    .find(|counter| counter.id == counter_id)
            })
            .map(|counter| counter.initial_value)
            .unwrap_or(0);
        self.runtime.set_counter(counter_id, initial_value);
    }
}

// ---------------------------------------------------------------------------
// Free helper functions.
// ---------------------------------------------------------------------------

pub(crate) fn phase_completion_slot_indices(phase: &CyclePhase) -> Vec<(usize, &SkillSlot)> {
    let has_mandatory = phase
        .skills
        .iter()
        .any(|slot| slot.slot_role == SkillSlotRole::Mandatory && !slot.skill_id.trim().is_empty());
    if has_mandatory {
        return phase
            .skills
            .iter()
            .enumerate()
            .filter(|(_, slot)| slot.slot_role == SkillSlotRole::Mandatory)
            .collect();
    }

    let has_non_filler = phase
        .skills
        .iter()
        .any(|slot| slot.slot_role != SkillSlotRole::Filler && !slot.skill_id.trim().is_empty());
    if has_non_filler {
        return phase
            .skills
            .iter()
            .enumerate()
            .filter(|(_, slot)| slot.slot_role != SkillSlotRole::Filler)
            .collect();
    }

    phase.skills.iter().enumerate().collect()
}

/// Score a phase for reacquisition: stable-loop/循环 phases get a 10 000
/// bonus. Higher scores are preferred.
pub(crate) fn phase_reacquire_score(phase_idx: usize, phase: &CyclePhase) -> usize {
    let lower_name = phase.name.to_lowercase();
    let stable_loop_bonus = usize::from(
        lower_name.contains("loop") || lower_name.contains("循环") || lower_name.contains("常规"),
    ) * 10_000;
    stable_loop_bonus + phase_idx
}
