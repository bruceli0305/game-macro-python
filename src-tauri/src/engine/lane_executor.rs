//! Observer and assist lane execution for `CycleExecutor`.

use crate::ast::evaluator::{EvalContext, TriBool, evaluate};
use crate::engine::cycle_executor::{CycleExecutor, CycleLogEvent};
use crate::engine::runtime_config::{
    AttemptContext, ObserverActionExprKey, PendingAttemptStage, SlotExprKey,
};
use crate::engine::skill_attempt::KeySender;
use crate::models::cycle::{
    AssistInterruptPolicy, AssistLaneConfig, ObserverActionSlot, ObserverLaneConfig, SkillSlot,
};

impl<'a> CycleExecutor<'a> {
    pub(super) fn try_assist_lanes(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
        main_stage: Option<PendingAttemptStage>,
    ) -> bool {
        for (lane_index, lane) in self.config.assist_lanes.iter().enumerate() {
            if !lane.enabled || lane.skills.is_empty() {
                continue;
            }
            if !Self::assist_policy_allows(lane.interrupt_policy, main_stage) {
                continue;
            }

            let lane_key = Self::assist_lane_key(lane_index, lane);
            if let Some(next_check_ms) = self.state.assist_lane_next_check_ms.get(&lane_key) {
                if now_ms < *next_check_ms {
                    continue;
                }
            }

            let mut sorted_slots: Vec<(usize, &SkillSlot)> =
                lane.skills.iter().enumerate().collect();
            sorted_slots.sort_by_key(|(_, slot)| slot.priority);
            let mut lane_checked = false;

            for (slot_index, slot) in sorted_slots {
                let sid = slot.skill_id.trim();
                if sid.is_empty() {
                    continue;
                }
                lane_checked = true;
                self.runtime.mark_node_exec(sid);

                let (ready, cond_reason) = self.check_skill_ready_at(
                    slot,
                    SlotExprKey::Assist {
                        lane_index,
                        slot_index,
                    },
                    now_ms,
                );
                if !ready {
                    self.runtime.mark_ready_false(sid);
                    let phase_name = format!("assist:{}", lane.name);
                    self.log_event(CycleLogEvent {
                        ts_ms: now_ms,
                        phase_index: self.state.phase_index,
                        phase_name: &phase_name,
                        event: "assist_skip",
                        skill_id: sid,
                        outcome: "NOT_READY",
                        reason: &cond_reason,
                    });
                    continue;
                }

                self.mark_assist_lane_checked(&lane_key, lane.check_interval_ms, now_ms);
                let context = AttemptContext::Assist {
                    lane_index,
                    lane_id: lane.id.clone(),
                    lane_name: lane.name.clone(),
                };
                if let Some(execution) = self.begin_skill_attempt(
                    key_sender,
                    slot,
                    stopped,
                    now_ms,
                    context.clone(),
                    SlotExprKey::Assist {
                        lane_index,
                        slot_index,
                    },
                ) {
                    self.finish_assist_attempt(
                        &context,
                        &slot.post_actions,
                        sid,
                        execution,
                        now_ms,
                    );
                }
                return true;
            }

            if lane_checked {
                self.mark_assist_lane_checked(&lane_key, lane.check_interval_ms, now_ms);
            }
        }

        false
    }

    pub(super) fn try_observer_lanes(&mut self, now_ms: u64) {
        for (lane_index, lane) in self.config.observer_lanes.iter().enumerate() {
            if !lane.enabled || lane.actions.is_empty() {
                continue;
            }

            let lane_key = Self::observer_lane_key(lane_index, lane);
            if let Some(next_check_ms) = self.state.observer_lane_next_check_ms.get(&lane_key) {
                if now_ms < *next_check_ms {
                    continue;
                }
            }

            let mut sorted_slots: Vec<(usize, &ObserverActionSlot)> =
                lane.actions.iter().enumerate().collect();
            sorted_slots.sort_by_key(|(_, slot)| slot.priority);
            let mut lane_checked = false;
            let phase_name = Self::observer_phase_name(lane);

            for (action_index, slot) in sorted_slots {
                let action_id = slot.id.trim();
                if action_id.is_empty() {
                    continue;
                }
                lane_checked = true;
                self.runtime.mark_node_exec(action_id);

                let (ready, cond_reason) =
                    self.check_observer_action_ready(ObserverActionExprKey {
                        lane_index,
                        action_index,
                    });
                if !ready {
                    self.runtime.mark_ready_false(action_id);
                    self.log_event(CycleLogEvent {
                        ts_ms: now_ms,
                        phase_index: self.state.phase_index,
                        phase_name: &phase_name,
                        event: "observer_skip",
                        skill_id: action_id,
                        outcome: "NOT_READY",
                        reason: &cond_reason,
                    });
                    continue;
                }

                self.log_event(CycleLogEvent {
                    ts_ms: now_ms,
                    phase_index: self.state.phase_index,
                    phase_name: &phase_name,
                    event: "observer_action",
                    skill_id: action_id,
                    outcome: "APPLIED",
                    reason: &cond_reason,
                });
                let actions = slot.actions.clone();
                self.apply_runtime_actions(
                    &actions,
                    now_ms,
                    self.state.phase_index,
                    &phase_name,
                    action_id,
                );
            }

            if lane_checked {
                self.mark_observer_lane_checked(&lane_key, lane.check_interval_ms, now_ms);
            }
        }
    }

    fn check_observer_action_ready(&self, key: ObserverActionExprKey) -> (bool, String) {
        if let Some(expr) = self
            .observer_action_expr_cache
            .get(&key)
            .and_then(|expr| expr.as_ref())
        {
            let ctx = EvalContext {
                points: self.points,
                skills: self.skills,
                sampler: self.sampler,
                metrics: Some(&self.runtime),
                timers: Some(&self.runtime),
                markers: Some(&self.runtime),
                counters: Some(&self.runtime),
                baseline: None,
                cast_bar_roi: self.cast_bar_roi,
            };
            let result = evaluate(expr, &ctx);
            match &result {
                TriBool::True => (true, "condition_true".into()),
                TriBool::False(reason) => (false, format!("condition_false: {reason}")),
                TriBool::Unknown(reason) => (false, format!("condition_unknown: {reason}")),
            }
        } else {
            (true, "no_condition".into())
        }
    }

    fn observer_lane_key(lane_index: usize, lane: &ObserverLaneConfig) -> String {
        let id = lane.id.trim();
        if id.is_empty() {
            format!("observer_lane_{lane_index}")
        } else {
            id.to_string()
        }
    }

    fn observer_phase_name(lane: &ObserverLaneConfig) -> String {
        let name = lane.name.trim();
        if name.is_empty() {
            format!("observer:{}", lane.id)
        } else {
            format!("observer:{name}")
        }
    }

    fn mark_observer_lane_checked(&mut self, lane_key: &str, check_interval_ms: u32, now_ms: u64) {
        self.state.observer_lane_next_check_ms.insert(
            lane_key.to_string(),
            now_ms.saturating_add(u64::from(check_interval_ms.max(1))),
        );
    }

    fn assist_policy_allows(
        policy: AssistInterruptPolicy,
        main_stage: Option<PendingAttemptStage>,
    ) -> bool {
        match main_stage {
            None => true,
            Some(PendingAttemptStage::CompleteWait) => matches!(
                policy,
                AssistInterruptPolicy::CompleteWait | AssistInterruptPolicy::AnyWait
            ),
            Some(PendingAttemptStage::StartWait | PendingAttemptStage::RetryDelay) => {
                matches!(policy, AssistInterruptPolicy::AnyWait)
            }
        }
    }

    fn assist_lane_key(lane_index: usize, lane: &AssistLaneConfig) -> String {
        let id = lane.id.trim();
        if id.is_empty() {
            format!("assist_lane_{lane_index}")
        } else {
            id.to_string()
        }
    }

    fn mark_assist_lane_checked(&mut self, lane_key: &str, check_interval_ms: u32, now_ms: u64) {
        self.state.assist_lane_next_check_ms.insert(
            lane_key.to_string(),
            now_ms.saturating_add(u64::from(check_interval_ms.max(1))),
        );
    }
}
