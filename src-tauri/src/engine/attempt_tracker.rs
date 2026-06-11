//! Skill attempt lifecycle methods for CycleExecutor.
//!
//! Handles beginning, advancing, and finishing skill attempts,
//! including start-wait, retry, and complete-wait stages.

use crate::engine::cycle_executor::{CycleExecutor, CycleLogEvent};
use crate::engine::runtime_config::{
    AttemptContext, PendingAttempt, PendingAttemptStage, slot_cache_key,
};
use crate::engine::skill_attempt::{
    Advance, AttemptEvent, CompletePolicy, ExecutionResult, KeySender, Outcome,
};
use crate::models::cycle::{CyclePhase, RuntimeAction, SkillSlot};

impl<'a> CycleExecutor<'a> {
    // ------------------------------------------------------------------
    // Slot attempt config merge.
    // ------------------------------------------------------------------

    pub(super) fn slot_attempt_cfg(
        &self,
        slot: &SkillSlot,
    ) -> crate::engine::skill_attempt::SkillAttemptConfig {
        use crate::engine::skill_attempt::{AttemptFailurePolicy, CompletePolicy as CP};
        let mut cfg = self.attempt_cfg.clone();
        let Some(policy) = &slot.attempt_policy else {
            return cfg;
        };

        cfg.max_retries = policy.max_attempts.saturating_sub(1);
        cfg.start_timeout_ms = policy.start_timeout_ms;
        cfg.retry_gap_ms = policy.retry_delay_ms;
        cfg.complete_timeout_ms =
            (policy.complete_timeout_ms > 0).then_some(policy.complete_timeout_ms);
        cfg.failure_policy = match policy.failure_policy.trim() {
            "hold_phase" => AttemptFailurePolicy::HoldPhase,
            "next_phase" => AttemptFailurePolicy::NextPhase,
            _ => AttemptFailurePolicy::NextSlot,
        };
        cfg.complete_policy = match policy.complete_fallback.trim() {
            "fail" => CP::HybridFail,
            "assume_success_after_timeout" => CP::HybridAssume,
            _ => cfg.complete_policy,
        };
        cfg
    }

    // ------------------------------------------------------------------
    // Begin a skill attempt.
    // ------------------------------------------------------------------

    pub(super) fn begin_skill_attempt(
        &mut self,
        key_sender: &mut dyn KeySender,
        slot: &SkillSlot,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
        context: AttemptContext,
    ) -> Option<ExecutionResult> {
        let sid = slot.skill_id.trim().to_string();
        let attempt_cfg = self.slot_attempt_cfg(slot);
        let Some(skill) = self.skills.iter().find(|skill| skill.id.as_str() == sid) else {
            return Some(ExecutionResult::failed(
                Advance::Advance,
                attempt_cfg.poll_not_ready_ms,
                "skill_missing",
            ));
        };

        if stopped() {
            self.apply_attempt_event(AttemptEvent::Stopped {
                skill_id: sid.clone(),
            });
            return Some(ExecutionResult::stopped());
        }

        self.apply_attempt_event(AttemptEvent::AttemptStarted {
            skill_id: sid.clone(),
        });

        if !key_sender.send_key(&skill.trigger_key) {
            self.apply_attempt_event(AttemptEvent::Failed {
                skill_id: sid.clone(),
                reason: "send_key_failed".into(),
            });
            return Some(ExecutionResult::failed(
                attempt_cfg.failure_policy.advance(),
                attempt_cfg.poll_not_ready_ms,
                "send_key_failed",
            ));
        }

        self.apply_attempt_event(AttemptEvent::KeySentOk {
            skill_id: sid.clone(),
        });

        let slot_exprs = self.slot_expr_cache.get(&slot_cache_key(slot));
        self.pending_attempt = Some(PendingAttempt {
            context,
            skill_id: sid,
            post_actions: slot.post_actions.clone(),
            readbar_ms: slot.override_cast_ms.unwrap_or(skill.cast.readbar_ms),
            start_expr: slot_exprs
                .and_then(|exprs| exprs.start_expr.clone())
                .unwrap_or(crate::ast::nodes::Expr::Const { value: true }),
            complete_expr: slot_exprs.and_then(|exprs| exprs.complete_expr.clone()),
            protected_release: slot.protected_release,
            attempt_cfg: attempt_cfg.clone(),
            stage: PendingAttemptStage::StartWait,
            retries_left: attempt_cfg.max_retries,
            deadline_ms: now_ms.saturating_add(u64::from(attempt_cfg.start_timeout_ms)),
            next_poll_ms: now_ms,
        });

        let pending = self.pending_attempt.take().expect("pending attempt set");
        self.advance_pending_attempt(key_sender, stopped, now_ms, pending);
        None
    }

    // ------------------------------------------------------------------
    // Advance a pending attempt through its stage machine.
    // ------------------------------------------------------------------

    pub(super) fn advance_pending_attempt(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
        mut pending: PendingAttempt,
    ) -> bool {
        if stopped() {
            self.apply_attempt_event(AttemptEvent::Stopped {
                skill_id: pending.skill_id,
            });
            return true;
        }

        if now_ms < pending.next_poll_ms {
            self.state.next_ready_ms = pending.next_poll_ms;
            self.pending_attempt = Some(pending);
            return false;
        }

        let result = match pending.stage {
            PendingAttemptStage::StartWait => {
                self.advance_start_wait(key_sender, now_ms, &mut pending)
            }
            PendingAttemptStage::RetryDelay => {
                self.advance_retry_delay(key_sender, now_ms, &mut pending)
            }
            PendingAttemptStage::CompleteWait => self.advance_complete_wait(now_ms, &mut pending),
        };

        match result {
            Some(execution) => {
                match pending.context.clone() {
                    AttemptContext::Main { phase_index } => {
                        let phase = self.config.phases.get(phase_index).cloned();
                        if let Some(phase) = phase {
                            self.finish_skill_attempt(
                                phase_index,
                                &phase,
                                &pending.post_actions,
                                &pending.skill_id,
                                execution,
                                now_ms,
                            );
                        }
                    }
                    AttemptContext::Assist { .. } => {
                        self.finish_assist_attempt(
                            &pending.context,
                            &pending.post_actions,
                            &pending.skill_id,
                            execution,
                            now_ms,
                        );
                        if let Some(main_pending) = self.suspended_main_attempt.take() {
                            self.pending_attempt = Some(main_pending);
                        }
                    }
                }
                true
            }
            None => {
                self.state.next_ready_ms = pending.next_poll_ms;
                self.pending_attempt = Some(pending);
                false
            }
        }
    }

    // ------------------------------------------------------------------
    // Start wait stage.
    // ------------------------------------------------------------------

    fn advance_start_wait(
        &mut self,
        key_sender: &mut dyn KeySender,
        now_ms: u64,
        pending: &mut PendingAttempt,
    ) -> Option<ExecutionResult> {
        if self.evaluate_expr(&pending.start_expr) {
            self.apply_attempt_event(AttemptEvent::CastStarted {
                skill_id: pending.skill_id.clone(),
            });
            self.apply_attempt_event(AttemptEvent::CompleteWaitStarted {
                skill_id: pending.skill_id.clone(),
            });
            pending.stage = PendingAttemptStage::CompleteWait;
            pending.deadline_ms =
                self.complete_deadline_ms(&pending.attempt_cfg, now_ms, pending.readbar_ms);
            pending.next_poll_ms = now_ms;
            return self.advance_complete_wait(now_ms, pending);
        }

        if now_ms >= pending.deadline_ms {
            if pending.retries_left == 0 {
                self.apply_attempt_event(AttemptEvent::Failed {
                    skill_id: pending.skill_id.clone(),
                    reason: "no_cast_start".into(),
                });
                return Some(ExecutionResult::failed(
                    pending.attempt_cfg.failure_policy.advance(),
                    pending.attempt_cfg.poll_not_ready_ms,
                    "no_cast_start",
                ));
            }
            pending.stage = PendingAttemptStage::RetryDelay;
            pending.next_poll_ms =
                now_ms.saturating_add(u64::from(pending.attempt_cfg.retry_gap_ms));
            return None;
        }

        pending.next_poll_ms = now_ms
            .saturating_add(u64::from(pending.attempt_cfg.start_poll_ms.max(1)))
            .min(pending.deadline_ms);
        let _ = key_sender;
        None
    }

    // ------------------------------------------------------------------
    // Retry delay stage.
    // ------------------------------------------------------------------

    fn advance_retry_delay(
        &mut self,
        key_sender: &mut dyn KeySender,
        now_ms: u64,
        pending: &mut PendingAttempt,
    ) -> Option<ExecutionResult> {
        if let Some(skill) = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == pending.skill_id)
        {
            if !key_sender.send_key(&skill.trigger_key) {
                self.apply_attempt_event(AttemptEvent::Failed {
                    skill_id: pending.skill_id.clone(),
                    reason: "send_key_failed_retry".into(),
                });
                return Some(ExecutionResult::failed(
                    pending.attempt_cfg.failure_policy.advance(),
                    pending.attempt_cfg.poll_not_ready_ms,
                    "send_key_failed_retry",
                ));
            }
            self.apply_attempt_event(AttemptEvent::KeySentOk {
                skill_id: pending.skill_id.clone(),
            });
            pending.retries_left = pending.retries_left.saturating_sub(1);
            pending.stage = PendingAttemptStage::StartWait;
            pending.deadline_ms =
                now_ms.saturating_add(u64::from(pending.attempt_cfg.start_timeout_ms));
            pending.next_poll_ms = now_ms;
            return self.advance_start_wait(key_sender, now_ms, pending);
        }

        Some(ExecutionResult::failed(
            pending.attempt_cfg.failure_policy.advance(),
            pending.attempt_cfg.poll_not_ready_ms,
            "skill_missing",
        ))
    }

    // ------------------------------------------------------------------
    // Complete wait stage.
    // ------------------------------------------------------------------

    fn advance_complete_wait(
        &mut self,
        now_ms: u64,
        pending: &mut PendingAttempt,
    ) -> Option<ExecutionResult> {
        match pending.attempt_cfg.complete_policy {
            CompletePolicy::AssumeSuccess => {
                if pending.readbar_ms == 0 || now_ms >= pending.deadline_ms {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        pending.attempt_cfg.default_gap_ms,
                        "success",
                    ));
                }
                pending.next_poll_ms = pending.deadline_ms;
                return None;
            }
            CompletePolicy::CdBlack => {
                if self.skill_pixel_is_black(&pending.skill_id) {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        pending.attempt_cfg.default_gap_ms,
                        "success",
                    ));
                }
                if now_ms >= pending.deadline_ms {
                    self.apply_attempt_event(AttemptEvent::Failed {
                        skill_id: pending.skill_id.clone(),
                        reason: "timeout".into(),
                    });
                    return Some(ExecutionResult::failed(
                        pending.attempt_cfg.failure_policy.advance(),
                        pending.attempt_cfg.poll_not_ready_ms,
                        "timeout",
                    ));
                }
            }
            CompletePolicy::HybridAssume if pending.complete_expr.is_none() => {
                if pending.readbar_ms == 0 || now_ms >= pending.deadline_ms {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        pending.attempt_cfg.default_gap_ms,
                        "hybrid_assume_no_expr",
                    ));
                }
                pending.next_poll_ms = pending.deadline_ms;
                return None;
            }
            _ => {
                let Some(expr) = pending.complete_expr.as_ref() else {
                    self.apply_attempt_event(AttemptEvent::Failed {
                        skill_id: pending.skill_id.clone(),
                        reason: "complete_signal_missing".into(),
                    });
                    return Some(ExecutionResult::failed(
                        pending.attempt_cfg.failure_policy.advance(),
                        pending.attempt_cfg.poll_not_ready_ms,
                        "complete_signal_missing",
                    ));
                };

                if self.evaluate_expr(expr) {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        pending.attempt_cfg.default_gap_ms,
                        "success",
                    ));
                }

                if now_ms >= pending.deadline_ms {
                    if pending.attempt_cfg.complete_policy == CompletePolicy::HybridAssume {
                        self.apply_attempt_event(AttemptEvent::Succeeded {
                            skill_id: pending.skill_id.clone(),
                        });
                        return Some(ExecutionResult::success(
                            pending.attempt_cfg.default_gap_ms,
                            "hybrid_assume_timeout",
                        ));
                    }
                    self.apply_attempt_event(AttemptEvent::Failed {
                        skill_id: pending.skill_id.clone(),
                        reason: "timeout".into(),
                    });
                    return Some(ExecutionResult::failed(
                        pending.attempt_cfg.failure_policy.advance(),
                        pending.attempt_cfg.poll_not_ready_ms,
                        "timeout",
                    ));
                }
            }
        }

        pending.next_poll_ms = now_ms
            .saturating_add(u64::from(pending.attempt_cfg.complete_poll_ms.max(1)))
            .min(pending.deadline_ms);
        None
    }

    // ------------------------------------------------------------------
    // Finish a main-phase skill attempt.
    // ------------------------------------------------------------------

    pub(super) fn finish_skill_attempt(
        &mut self,
        phase_idx: usize,
        phase: &CyclePhase,
        post_actions: &[RuntimeAction],
        skill_id: &str,
        execution: ExecutionResult,
        now_ms: u64,
    ) {
        let outcome = format!("{:?}", execution.outcome);
        self.state.next_ready_ms = now_ms.saturating_add(u64::from(execution.next_delay_ms));
        let should_advance_slot = execution.outcome == Outcome::Success
            || execution.advance == Advance::Advance
            || execution.advance == Advance::NextPhase;
        if should_advance_slot {
            self.state.fired_in_phase.insert(skill_id.to_string());
            self.state.fired_in_cycle.insert(skill_id.to_string());
            *self
                .state
                .fired_count_in_cycle
                .entry(skill_id.to_string())
                .or_insert(0) += 1;
            if let Some(cooldown_ms) = self.skill_cooldown_ms(skill_id) {
                self.state.skill_ready_at_ms.insert(
                    skill_id.to_string(),
                    now_ms.saturating_add(u64::from(cooldown_ms)),
                );
            }
        }
        self.state.total_executed += 1;
        self.state.last_skill_id = skill_id.to_string();
        self.state.last_outcome = outcome.clone();

        self.log_event(CycleLogEvent {
            ts_ms: now_ms,
            phase_index: phase_idx,
            phase_name: &phase.name,
            event: "execute",
            skill_id,
            outcome: &outcome,
            reason: &execution.reason,
        });

        if execution.outcome == Outcome::Success {
            self.apply_runtime_actions(post_actions, now_ms, phase_idx, &phase.name, skill_id);
        }

        // Advance::NextPhase always forces transition.
        // For complete_when != "none_ready", check is_phase_complete immediately
        // so any_fired / all_fired / always take effect in the same tick.
        // For "none_ready", defer to the tick-loop check (cycle_executor L326)
        // so the phase survives until no slot is ready, giving cooldowns more
        // ticks to expire and attunement‑guard slots time to resolve.
        if execution.advance == Advance::NextPhase
            || (phase.complete_when != "none_ready" && self.is_phase_complete(phase))
        {
            self.on_phase_complete(phase_idx, phase, now_ms);
            if self.state.phase_index >= self.config.phases.len() {
                self.on_cycle_reset();
            }
        }
    }

    // ------------------------------------------------------------------
    // Finish an assist-lane skill attempt.
    // ------------------------------------------------------------------

    pub(super) fn finish_assist_attempt(
        &mut self,
        context: &AttemptContext,
        post_actions: &[RuntimeAction],
        skill_id: &str,
        execution: ExecutionResult,
        now_ms: u64,
    ) {
        let AttemptContext::Assist {
            lane_index,
            lane_id,
            lane_name,
        } = context
        else {
            return;
        };
        let outcome = format!("{:?}", execution.outcome);
        self.state.next_ready_ms = now_ms.saturating_add(u64::from(execution.next_delay_ms));
        let should_count = execution.outcome == Outcome::Success
            || execution.advance == Advance::Advance
            || execution.advance == Advance::NextPhase;
        if should_count {
            self.state.fired_in_cycle.insert(skill_id.to_string());
            *self
                .state
                .fired_count_in_cycle
                .entry(skill_id.to_string())
                .or_insert(0) += 1;
            if let Some(cooldown_ms) = self.skill_cooldown_ms(skill_id) {
                self.state.skill_ready_at_ms.insert(
                    skill_id.to_string(),
                    now_ms.saturating_add(u64::from(cooldown_ms)),
                );
            }
        }
        self.state.total_executed += 1;
        self.state.last_skill_id = skill_id.to_string();
        self.state.last_outcome = outcome.clone();

        let phase_name = if lane_name.trim().is_empty() {
            format!("assist:{lane_id}")
        } else {
            format!("assist:{lane_name}")
        };
        self.log_event(CycleLogEvent {
            ts_ms: now_ms,
            phase_index: *lane_index,
            phase_name: &phase_name,
            event: "assist_execute",
            skill_id,
            outcome: &outcome,
            reason: &execution.reason,
        });

        if execution.outcome == Outcome::Success {
            self.apply_runtime_actions(post_actions, now_ms, *lane_index, &phase_name, skill_id);
        }
    }

    // ------------------------------------------------------------------
    // Deadline calculation.
    // ------------------------------------------------------------------

    fn complete_deadline_ms(
        &self,
        attempt_cfg: &crate::engine::skill_attempt::SkillAttemptConfig,
        now_ms: u64,
        readbar_ms: u32,
    ) -> u64 {
        if let Some(timeout_ms) = attempt_cfg.complete_timeout_ms {
            return now_ms.saturating_add(u64::from(timeout_ms));
        }
        if readbar_ms == 0 {
            return now_ms;
        }
        let wait_ms = match attempt_cfg.complete_policy {
            CompletePolicy::AssumeSuccess => readbar_ms,
            _ => (readbar_ms as f64 * attempt_cfg.complete_max_wait_factor).max(1.0) as u32,
        };
        now_ms.saturating_add(u64::from(wait_ms))
    }
}
