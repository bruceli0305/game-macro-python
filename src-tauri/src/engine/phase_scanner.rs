//! Active phase scanning for `CycleExecutor::tick`.

use crate::engine::cycle_executor::{CycleExecutor, CycleLogEvent};
use crate::engine::runtime_config::{AttemptContext, SlotExprKey};
use crate::engine::skill_attempt::KeySender;
use crate::models::cycle::SkillSlot;

pub(super) enum PhaseScanOutcome {
    Acted,
    AllowAssist,
    Blocked,
}

impl<'a> CycleExecutor<'a> {
    pub(super) fn scan_active_phase(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
    ) -> PhaseScanOutcome {
        if now_ms < self.state.next_ready_ms {
            return PhaseScanOutcome::Blocked;
        }

        let phases = &self.config.phases;
        if phases.is_empty() {
            return PhaseScanOutcome::Blocked;
        }

        if self.state.phase_index >= phases.len() {
            self.on_cycle_reset();
        }

        let phase_idx = self.state.phase_index;
        if phase_idx >= phases.len() {
            return PhaseScanOutcome::Blocked;
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

            return PhaseScanOutcome::Acted;
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
            return PhaseScanOutcome::Acted;
        }

        PhaseScanOutcome::AllowAssist
    }
}
