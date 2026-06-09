//! Phase and priority cycle executor.
//!
//! Execution model:
//! 1. Keep the active phase index and fired skill sets.
//! 2. On each tick, scan the active phase by priority.
//! 3. Start the first ready skill attempt.
//! 4. Advance pending attempts across later ticks without blocking.
//! 5. Advance or reset phases after attempts finish.

use crate::ast::compiler::compile_expr_json;
use crate::ast::evaluator::{CastBarRoiProvider, EvalContext, PixelSampler, evaluate};
use crate::ast::nodes::Expr;
use crate::engine::runtime_state::RuntimeState;
use crate::engine::skill_attempt::{
    Advance, AttemptEvent, AttemptFailurePolicy, CompletePolicy, ExecutionResult, KeySender,
    SkillAttemptConfig,
};
use crate::models::cycle::{
    AssistInterruptPolicy, AssistLaneConfig, CycleConfig, CyclePhase, PhaseFallbackTransition,
    PhaseTransitionRule, RuntimeAction, SkillSlot,
};
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

struct CycleLogEvent<'a> {
    ts_ms: u64,
    phase_index: usize,
    phase_name: &'a str,
    event: &'a str,
    skill_id: &'a str,
    outcome: &'a str,
    reason: &'a str,
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
    pending_attempt: Option<PendingAttempt>,
    suspended_main_attempt: Option<PendingAttempt>,

    // Compiled condition cache: skill_id -> condition expression.
    pub expr_cache: Vec<(String, Option<Expr>)>,
}

#[derive(Debug, Clone)]
struct PendingAttempt {
    context: AttemptContext,
    skill_id: String,
    post_actions: Vec<RuntimeAction>,
    readbar_ms: u32,
    start_expr: Expr,
    complete_expr: Option<Expr>,
    protected_release: bool,
    attempt_cfg: SkillAttemptConfig,
    stage: PendingAttemptStage,
    retries_left: u32,
    deadline_ms: u64,
    next_poll_ms: u64,
}

#[derive(Debug, Clone)]
enum AttemptContext {
    Main {
        phase_index: usize,
    },
    Assist {
        lane_index: usize,
        lane_id: String,
        lane_name: String,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PendingAttemptStage {
    StartWait,
    RetryDelay,
    CompleteWait,
}

impl<'a> CycleExecutor<'a> {
    pub fn new(
        config: &'a CycleConfig,
        points: &'a [Point],
        skills: &'a [Skill],
        sampler: &'a dyn PixelSampler,
        attempt_cfg: SkillAttemptConfig,
    ) -> Self {
        // Precompile all slot condition expressions.
        let expr_cache: Vec<_> = config
            .phases
            .iter()
            .flat_map(|p| p.skills.iter())
            .map(|slot| {
                let expr = slot
                    .condition_expr
                    .as_ref()
                    .and_then(|v| compile_expr_json(v, "$").expr);
                (slot.skill_id.clone(), expr)
            })
            .collect();

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
            expr_cache,
        }
    }

    pub fn with_cast_bar_roi_provider(
        mut self,
        provider: Option<&'a dyn CastBarRoiProvider>,
    ) -> Self {
        self.cast_bar_roi = provider;
        self
    }

    /// Advance the cycle executor by one scheduler tick.
    pub fn tick(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
    ) -> bool {
        self.runtime.set_now_ms(now_ms);
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
        let mut sorted_slots: Vec<&SkillSlot> = phase.skills.iter().collect();
        sorted_slots.sort_by_key(|slot| slot.priority);

        for slot in &sorted_slots {
            let sid = slot.skill_id.trim();
            if sid.is_empty() {
                continue;
            }

            if self.state.fired_in_phase.contains(sid)
                && phase.complete_when != "always"
                && !self.slot_can_fire_more_this_cycle(sid)
            {
                continue;
            }

            self.runtime.mark_node_exec(sid);

            let (ready, cond_reason) = self.check_skill_ready(slot, now_ms);
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

        self.try_assist_lanes(key_sender, stopped, now_ms, None)
    }

    fn check_skill_ready(&self, slot: &SkillSlot, now_ms: u64) -> (bool, String) {
        let sid = slot.skill_id.trim();
        if sid.is_empty() {
            return (false, "skill_id_empty".into());
        }

        let Some(skill) = self.skills.iter().find(|s| s.id.as_str() == sid) else {
            return (false, "skill_missing".into());
        };
        if !skill.enabled {
            return (false, "skill_disabled".into());
        }
        if let Some(ready_at) = self.state.skill_ready_at_ms.get(sid) {
            if now_ms < *ready_at {
                return (false, format!("cooldown_until={ready_at}"));
            }
        }
        if !self.slot_can_fire_more_this_cycle(sid) {
            let shot_limit = skill.shots_per_cycle.max(1);
            return (false, format!("shots_per_cycle_exhausted={shot_limit}"));
        }
        if !self.skill_has_ammo(skill) {
            return (false, "ammo_unavailable".into());
        }

        let expr = slot
            .condition_expr
            .as_ref()
            .and_then(|value| compile_expr_json(value, "$.condition_expr").expr);

        if let Some(e) = expr.as_ref() {
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
            let result = evaluate(e, &ctx);
            match &result {
                crate::ast::evaluator::TriBool::True => (true, "condition_true".into()),
                crate::ast::evaluator::TriBool::False(reason) => {
                    (false, format!("condition_false: {reason}"))
                }
                crate::ast::evaluator::TriBool::Unknown(reason) => {
                    (false, format!("condition_unknown: {reason}"))
                }
            }
        } else {
            (true, "no_condition".into())
        }
    }

    fn try_assist_lanes(
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

            let mut sorted_slots: Vec<&SkillSlot> = lane.skills.iter().collect();
            sorted_slots.sort_by_key(|slot| slot.priority);
            let mut lane_checked = false;

            for slot in sorted_slots {
                let sid = slot.skill_id.trim();
                if sid.is_empty() {
                    continue;
                }
                lane_checked = true;
                self.runtime.mark_node_exec(sid);

                let (ready, cond_reason) = self.check_skill_ready(slot, now_ms);
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
                if let Some(execution) =
                    self.begin_skill_attempt(key_sender, slot, stopped, now_ms, context.clone())
                {
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

    fn slot_attempt_cfg(&self, slot: &SkillSlot) -> SkillAttemptConfig {
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
            "fail" => CompletePolicy::HybridFail,
            "assume_success_after_timeout" => CompletePolicy::HybridAssume,
            _ => cfg.complete_policy,
        };
        cfg
    }

    fn begin_skill_attempt(
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

        self.pending_attempt = Some(PendingAttempt {
            context,
            skill_id: sid,
            post_actions: slot.post_actions.clone(),
            readbar_ms: slot.override_cast_ms.unwrap_or(skill.cast.readbar_ms),
            start_expr: slot
                .start_expr
                .as_ref()
                .and_then(|value| compile_expr_json(value, "$.start_expr").expr)
                .unwrap_or(Expr::Const { value: true }),
            complete_expr: slot
                .complete_expr
                .as_ref()
                .and_then(|value| compile_expr_json(value, "$.complete_expr").expr),
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

    fn advance_pending_attempt(
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

    fn finish_skill_attempt(
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
        let should_advance_slot = execution.outcome
            == crate::engine::skill_attempt::Outcome::Success
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

        if execution.outcome == crate::engine::skill_attempt::Outcome::Success {
            self.apply_runtime_actions(post_actions, now_ms, phase_idx, &phase.name, skill_id);
        }

        if execution.advance == Advance::NextPhase || self.is_phase_complete(phase) {
            self.on_phase_complete(phase_idx, phase, now_ms);
            if self.state.phase_index >= self.config.phases.len() {
                self.on_cycle_reset();
            }
        }
    }

    fn finish_assist_attempt(
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
        let should_count = execution.outcome == crate::engine::skill_attempt::Outcome::Success
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

        if execution.outcome == crate::engine::skill_attempt::Outcome::Success {
            self.apply_runtime_actions(post_actions, now_ms, *lane_index, &phase_name, skill_id);
        }
    }

    fn complete_deadline_ms(
        &self,
        attempt_cfg: &SkillAttemptConfig,
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

    fn evaluate_expr(&self, expr: &Expr) -> bool {
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
        evaluate(expr, &ctx).is_true()
    }

    fn enter_phase_if_needed(&mut self, phase_idx: usize, phase: &CyclePhase, now_ms: u64) {
        if self.state.phase_entry_applied {
            return;
        }
        self.state.phase_entry_applied = true;
        self.reset_phase_entry_counters();
        self.apply_runtime_actions(&phase.entry_actions, now_ms, phase_idx, &phase.name, "");
    }

    fn apply_runtime_actions(
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

    fn skill_pixel_is_black(&self, skill_id: &str) -> bool {
        let Some(skill) = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)
        else {
            return false;
        };
        let pix = &skill.pixel;
        self.sampler
            .sample_rgb_abs(
                &pix.monitor,
                pix.vx,
                pix.vy,
                &pix.sample.mode,
                pix.sample.radius,
            )
            .is_some_and(|(r, g, b)| r.max(g).max(b) <= 5)
    }

    fn skill_cooldown_ms(&self, skill_id: &str) -> Option<u32> {
        let skill = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)?;
        let cooldown_ms = skill.cooldown_ms.max(skill.cast.cooldown_ms);
        (cooldown_ms > 0).then_some(cooldown_ms)
    }

    fn slot_can_fire_more_this_cycle(&self, skill_id: &str) -> bool {
        let shot_limit = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)
            .map(|skill| skill.shots_per_cycle.max(1))
            .unwrap_or(1);
        self.state
            .fired_count_in_cycle
            .get(skill_id)
            .copied()
            .unwrap_or(0)
            < shot_limit
    }

    fn slot_shots_complete_this_cycle(&self, skill_id: &str) -> bool {
        let shot_limit = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)
            .map(|skill| skill.shots_per_cycle.max(1))
            .unwrap_or(1);
        self.state
            .fired_count_in_cycle
            .get(skill_id)
            .copied()
            .unwrap_or(0)
            >= shot_limit
    }

    fn skill_has_ammo(&self, skill: &Skill) -> bool {
        if skill.ammo_stages.is_empty() {
            return true;
        }

        skill.ammo_stages.iter().any(|stage| {
            if stage.charges_left == 0 {
                return false;
            }
            let pix = &stage.pixel;
            self.sampler
                .sample_rgb_abs(
                    &pix.monitor,
                    pix.vx,
                    pix.vy,
                    &pix.sample.mode,
                    pix.sample.radius,
                )
                .is_some_and(|current| {
                    rgb_diff_max(current, (pix.color.r, pix.color.g, pix.color.b)) <= pix.tolerance
                })
        })
    }

    fn apply_attempt_event(&mut self, event: AttemptEvent) {
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

    fn is_phase_complete(&self, phase: &CyclePhase) -> bool {
        match phase.complete_when.as_str() {
            "always" => true,
            "any_fired" => !self.state.fired_in_phase.is_empty(),
            "none_ready" => phase.skills.iter().all(|slot| {
                let sid = slot.skill_id.trim();
                sid.is_empty()
                    || self.state.fired_in_phase.contains(sid)
                    || !self.check_skill_ready(slot, self.state.next_ready_ms).0
            }),
            _ => phase.skills.iter().all(|slot| {
                let skill_id = slot.skill_id.trim();
                skill_id.is_empty() || self.slot_shots_complete_this_cycle(skill_id)
            }),
        }
    }

    fn on_phase_complete(&mut self, phase_idx: usize, phase: &CyclePhase, now_ms: u64) {
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
        // Outer tick code records phase-level logs.
    }

    fn resolve_phase_transition(&self, phase_idx: usize, phase: &CyclePhase) -> (usize, String) {
        for rule in &phase.transition_rules {
            if self.transition_rule_matches(rule) {
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

    fn transition_rule_matches(&self, rule: &PhaseTransitionRule) -> bool {
        let Some(expr_json) = &rule.condition_expr else {
            return false;
        };
        let compiled = compile_expr_json(expr_json, "$");
        let Some(expr) = compiled.expr else {
            return false;
        };
        self.evaluate_expr(&expr)
    }

    fn find_phase_index(&self, target_phase: &str) -> Option<usize> {
        let target_phase = target_phase.trim();
        if target_phase.is_empty() {
            return None;
        }
        self.config
            .phases
            .iter()
            .position(|phase| phase.name.trim() == target_phase)
    }

    fn on_cycle_reset(&mut self) {
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
        // Runtime metrics are cumulative and are not reset per cycle.
    }

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

    fn log_event(&mut self, event: CycleLogEvent<'_>) {
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

fn rgb_diff_max(a: (u8, u8, u8), b: (u8, u8, u8)) -> u8 {
    let dr = (a.0 as i16 - b.0 as i16).unsigned_abs() as u8;
    let dg = (a.1 as i16 - b.1 as i16).unsigned_abs() as u8;
    let db = (a.2 as i16 - b.2 as i16).unsigned_abs() as u8;
    dr.max(dg).max(db)
}

// ===========================================================================
// Tests.
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::evaluator::{CastBarRoiProvider, CastBarRoiState, PixelSampler};
    use crate::models::cycle::{
        AssistInterruptPolicy, AssistLaneConfig, AttemptPolicy, CyclePhase, CycleStateSchema,
        PhaseFallbackTransition, PhaseTransitionRule, RuntimeAction, RuntimeCounterDef,
        RuntimeMarkerDef, RuntimeTimerDef, SkillSlot,
    };
    use crate::models::skill::{AmmoStagePixel, ColorRGB, PixelSpec, SampleConfig, Skill};
    use serde_json::json;

    struct DummySampler {
        rgb: (u8, u8, u8),
    }
    impl PixelSampler for DummySampler {
        fn sample_rgb_abs(
            &self,
            _m: &str,
            _x: i32,
            _y: i32,
            _mode: &str,
            _r: u8,
        ) -> Option<(u8, u8, u8)> {
            Some(self.rgb)
        }
    }

    struct DummyKeySender {
        keys: Vec<String>,
        fail: bool,
    }
    impl KeySender for DummyKeySender {
        fn send_key(&mut self, key: &str) -> bool {
            self.keys.push(key.into());
            !self.fail
        }
    }

    struct DummyCastBarRoiProvider {
        state: Option<CastBarRoiState>,
    }

    impl CastBarRoiProvider for DummyCastBarRoiProvider {
        fn get_cast_bar_roi_state(&self) -> Option<CastBarRoiState> {
            self.state
        }
    }

    fn make_skill(id: &str, key: &str) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            enabled: true,
            trigger_key: key.into(),
            cast: Default::default(),
            pixel: PixelSpec {
                monitor: "primary".into(),
                vx: 0,
                vy: 0,
                color: ColorRGB {
                    r: 100,
                    g: 150,
                    b: 200,
                },
                tolerance: 10,
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

    fn make_slot(skill_id: &str, priority: u32) -> SkillSlot {
        SkillSlot {
            skill_id: skill_id.into(),
            priority,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        }
    }

    fn make_assist_lane(policy: AssistInterruptPolicy, skills: Vec<SkillSlot>) -> AssistLaneConfig {
        AssistLaneConfig {
            id: "assist".into(),
            name: "Assist".into(),
            enabled: true,
            check_interval_ms: 50,
            interrupt_policy: policy,
            skills,
        }
    }

    #[test]
    fn test_empty_config_no_panic() {
        let config = CycleConfig::default();
        let points = vec![];
        let skills = vec![];
        let sampler = DummySampler { rgb: (0, 0, 0) };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };
        let acted = exec.tick(&mut ks, &|| false, 0);
        assert!(!acted);
    }

    #[test]
    fn test_assist_lane_executes_when_main_has_no_ready_slot() {
        let config = CycleConfig {
            name: "assist_idle".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![SkillSlot {
                    condition_expr: Some(json!({ "type": "const", "value": false })),
                    ..make_slot("main", 1)
                }],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![make_assist_lane(
                AssistInterruptPolicy::IdleOnly,
                vec![make_slot("assist", 1)],
            )],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("main", "M"), make_skill("assist", "A")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));

        assert_eq!(ks.keys, vec!["A"]);
        assert!(exec.log.iter().any(|entry| entry.event == "assist_execute"
            && entry.skill_id == "assist"
            && entry.phase_name == "assist:Assist"));
        assert!(!exec.state.fired_in_phase.contains("assist"));
    }

    #[test]
    fn test_assist_idle_only_does_not_interrupt_main_complete_wait() {
        let mut main_skill = make_skill("main", "M");
        main_skill.cast.readbar_ms = 100;
        let config = CycleConfig {
            name: "assist_no_interrupt".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("main", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![make_assist_lane(
                AssistInterruptPolicy::IdleOnly,
                vec![make_slot("assist", 1)],
            )],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![main_skill, make_skill("assist", "A")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert!(!exec.tick(&mut ks, &|| false, 10));

        assert_eq!(ks.keys, vec!["M"]);
        assert!(!exec.log.iter().any(|entry| entry.event == "assist_execute"));
    }

    #[test]
    fn test_assist_complete_wait_can_run_during_main_complete_wait() {
        let mut main_skill = make_skill("main", "M");
        main_skill.cast.readbar_ms = 100;
        let config = CycleConfig {
            name: "assist_complete_wait".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("main", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![make_assist_lane(
                AssistInterruptPolicy::CompleteWait,
                vec![make_slot("assist", 1)],
            )],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![main_skill, make_skill("assist", "A")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert!(exec.tick(&mut ks, &|| false, 10));
        assert!(exec.tick(&mut ks, &|| false, 100));

        assert_eq!(ks.keys, vec!["M", "A"]);
        assert_eq!(exec.state.total_executed, 2);
        assert!(
            exec.log
                .iter()
                .any(|entry| entry.event == "assist_execute" && entry.skill_id == "assist")
        );
        assert!(exec.log.iter().any(|entry| entry.event == "execute"
            && entry.skill_id == "main"
            && entry.outcome == "Success"));
    }

    #[test]
    fn test_protected_release_blocks_assist_complete_wait_interrupt() {
        let mut main_skill = make_skill("main", "M");
        main_skill.cast.readbar_ms = 100;
        let mut main_slot = make_slot("main", 1);
        main_slot.protected_release = true;
        let config = CycleConfig {
            name: "assist_protected".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![main_slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![make_assist_lane(
                AssistInterruptPolicy::CompleteWait,
                vec![make_slot("assist", 1)],
            )],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![main_skill, make_skill("assist", "A")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert!(!exec.tick(&mut ks, &|| false, 10));
        assert!(exec.tick(&mut ks, &|| false, 100));

        assert_eq!(ks.keys, vec!["M"]);
        assert_eq!(exec.state.total_executed, 1);
        assert!(!exec.log.iter().any(|entry| entry.event == "assist_execute"));
    }

    #[test]
    fn test_single_phase_single_skill() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        // tick 1: execute sk1; any_fired completes the phase and resets the cycle.
        let acted = exec.tick(&mut ks, &|| false, 0);
        assert!(acted);
        assert_eq!(exec.state.total_executed, 1);
        assert_eq!(exec.state.cycle_count, 1);
        assert_eq!(exec.state.next_ready_ms, 50);
        assert_eq!(ks.keys, vec!["f1"]);

        // tick 2: the default post-attempt gap blocks immediate re-fire.
        let acted = exec.tick(&mut ks, &|| false, 1);
        assert!(!acted);
        assert_eq!(exec.state.total_executed, 1);

        // tick 3: new cycle phase 0, sk1 is due again after the gap.
        let acted = exec.tick(&mut ks, &|| false, 50);
        assert!(acted);
        assert_eq!(exec.state.total_executed, 2);
        assert_eq!(exec.state.cycle_count, 2);
    }

    #[test]
    fn test_priority_order() {
        // Lower priority number executes first.
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("skB", 2), make_slot("skA", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("skA", "A"), make_skill("skB", "B")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        // tick 1: the executor should pick skA first because it has priority 1.
        let acted = exec.tick(&mut ks, &|| false, 0);
        assert!(acted);
        assert_eq!(ks.keys, vec!["A"]);
    }

    #[test]
    fn test_stopped() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        let acted = exec.tick(&mut ks, &|| true, 0);
        assert!(!acted);
    }

    #[test]
    fn test_condition_expr_blocks_skill() {
        // condition false means the skill is not ready.
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![SkillSlot {
                    skill_id: "sk1".into(),
                    priority: 1,
                    label: String::new(),
                    condition_expr: Some(json!({"type": "const", "value": false})),
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
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        let acted = exec.tick(&mut ks, &|| false, 0);
        assert!(!acted);
    }

    #[test]
    fn test_all_fired_completion() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![
                CyclePhase {
                    name: "P1".into(),
                    skills: vec![make_slot("skA", 1), make_slot("skB", 2)],
                    complete_when: "all_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![make_slot("skC", 1)],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
            ],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![
            make_skill("skA", "A"),
            make_skill("skB", "B"),
            make_skill("skC", "C"),
        ];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        // tick 1: skA (priority 1)
        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.phase_index, 0); // Still in P1 because all_fired is not complete.

        // tick 2: skB (priority 2, skA has already fired).
        assert!(exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.phase_index, 1); // P1 completes and advances to P2.

        // tick 3: skC (P2)
        assert!(exec.tick(&mut ks, &|| false, 100));
        // P2 completes and the cycle resets to P1.
        assert_eq!(exec.state.cycle_count, 1);
    }

    #[test]
    fn test_runtime_metrics_after_success() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.node_exec, 1);
        assert_eq!(runtime.attempt_started, 1);
        assert_eq!(runtime.key_sent_ok, 1);
        assert_eq!(runtime.cast_started, 1);
        assert_eq!(runtime.success, 1);
        assert_eq!(runtime.fail, 0);
    }

    #[test]
    fn test_assume_success_waits_readbar_across_ticks() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.cast.readbar_ms = 100;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 0);
        assert_eq!(exec.state.next_ready_ms, 100);
        assert!(exec.pending_attempt.is_some());
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.key_sent_ok, 1);
        assert_eq!(runtime.cast_started, 1);
        assert_eq!(runtime.success, 0);

        assert!(!exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.total_executed, 0);

        assert!(exec.tick(&mut ks, &|| false, 100));
        assert_eq!(exec.state.total_executed, 1);
        assert_eq!(exec.state.next_ready_ms, 150);
        assert!(exec.pending_attempt.is_none());
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.success, 1);
    }

    #[test]
    fn test_start_expr_waits_until_timeout() {
        let mut slot = make_slot("sk1", 1);
        slot.start_expr = Some(json!({"type": "const", "value": false}));
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let cfg = SkillAttemptConfig {
            max_retries: 0,
            start_timeout_ms: 20,
            start_poll_ms: 10,
            ..Default::default()
        };
        let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 0);
        assert_eq!(exec.state.next_ready_ms, 10);
        assert!(exec.pending_attempt.is_some());

        assert!(!exec.tick(&mut ks, &|| false, 10));
        assert_eq!(exec.state.total_executed, 0);
        assert_eq!(exec.state.next_ready_ms, 20);

        assert!(exec.tick(&mut ks, &|| false, 20));
        assert_eq!(exec.state.total_executed, 1);
        assert_eq!(exec.state.last_outcome, "Failed");
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.key_sent_ok, 1);
        assert_eq!(runtime.cast_started, 0);
        assert_eq!(runtime.fail, 1);
        assert_eq!(runtime.fail_by_reason.get("no_cast_start"), Some(&1));
    }

    #[test]
    fn test_start_expr_accepts_cast_bar_roi_changed() {
        let mut slot = make_slot("sk1", 1);
        slot.start_expr = Some(json!({"type": "cast_bar_roi_changed"}));
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let roi = DummyCastBarRoiProvider {
            state: Some(CastBarRoiState {
                changed_from_baseline: true,
                border_visible: false,
                gone: false,
                changed_ratio: 0.4,
                border_match_ratio: 0.0,
            }),
        };
        let cfg = SkillAttemptConfig {
            max_retries: 0,
            start_timeout_ms: 20,
            start_poll_ms: 10,
            ..Default::default()
        };
        let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg)
            .with_cast_bar_roi_provider(Some(&roi));
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(ks.keys, vec!["f1"]);
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.cast_started, 1);
        assert_eq!(runtime.fail, 0);
    }

    #[test]
    fn test_slot_attempt_policy_max_attempts_one_sends_one_key() {
        let mut slot = make_slot("sk1", 1);
        slot.start_expr = Some(json!({"type": "const", "value": false}));
        slot.attempt_policy = Some(AttemptPolicy {
            max_attempts: 1,
            start_timeout_ms: 20,
            complete_timeout_ms: 0,
            retry_delay_ms: 5,
            failure_policy: "next_slot".into(),
            complete_fallback: "assume_success_after_timeout".into(),
        });
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let cfg = SkillAttemptConfig {
            max_retries: 10,
            start_timeout_ms: 1000,
            start_poll_ms: 10,
            ..Default::default()
        };
        let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(ks.keys, vec!["f1"]);
        assert!(!exec.tick(&mut ks, &|| false, 10));
        assert_eq!(ks.keys, vec!["f1"]);
        assert!(exec.tick(&mut ks, &|| false, 20));
        assert_eq!(ks.keys, vec!["f1"]);
        assert_eq!(exec.state.last_outcome, "Failed");
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.key_sent_ok, 1);
        assert_eq!(runtime.fail_by_reason.get("no_cast_start"), Some(&1));
    }

    #[test]
    fn test_slot_attempt_policy_complete_timeout_overrides_readbar() {
        let mut slot = make_slot("sk1", 1);
        slot.complete_expr = Some(json!({"type": "const", "value": false}));
        slot.attempt_policy = Some(AttemptPolicy {
            max_attempts: 1,
            start_timeout_ms: 20,
            complete_timeout_ms: 25,
            retry_delay_ms: 0,
            failure_policy: "next_slot".into(),
            complete_fallback: "fail".into(),
        });
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.cast.readbar_ms = 1000;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.next_ready_ms, 25);
        assert_eq!(exec.state.total_executed, 0);
        assert!(exec.tick(&mut ks, &|| false, 25));
        assert_eq!(exec.state.last_outcome, "Failed");
        assert_eq!(exec.state.next_ready_ms, 75);
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.key_sent_ok, 1);
        assert_eq!(runtime.fail_by_reason.get("timeout"), Some(&1));
    }

    #[test]
    fn test_timer_post_action_gates_next_phase_skill() {
        let mut first = make_slot("sk1", 1);
        first.post_actions = vec![RuntimeAction::RecordTimer {
            timer_id: "burst".into(),
        }];

        let mut second = make_slot("sk2", 1);
        second.condition_expr = Some(json!({
            "type": "timer_elapsed_ge",
            "timer_id": "burst",
            "ms": 100
        }));

        let config = CycleConfig {
            name: "test".into(),
            phases: vec![
                CyclePhase {
                    name: "P1".into(),
                    skills: vec![first],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![second],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
            ],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: Some(CycleStateSchema {
                markers: vec![],
                timers: vec![RuntimeTimerDef {
                    id: "burst".into(),
                    name: "Burst timer".into(),
                    reset_on_cycle_start: false,
                }],
                counters: vec![],
            }),
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(ks.keys, vec!["f1"]);
        assert_eq!(exec.runtime.timers.get("burst"), Some(&0));
        assert_eq!(exec.state.phase_index, 1);

        assert!(!exec.tick(&mut ks, &|| false, 50));
        assert_eq!(ks.keys, vec!["f1"]);

        assert!(exec.tick(&mut ks, &|| false, 100));
        assert_eq!(ks.keys, vec!["f1", "f2"]);
    }

    #[test]
    fn test_marker_post_action_gates_next_phase_skill() {
        let mut first = make_slot("sk1", 1);
        first.post_actions = vec![RuntimeAction::SetMarker {
            marker_id: "weapon".into(),
            value: "alt".into(),
        }];

        let mut second = make_slot("sk2", 1);
        second.condition_expr = Some(json!({
            "type": "marker_eq",
            "marker_id": "weapon",
            "value": "alt"
        }));

        let config = CycleConfig {
            name: "test".into(),
            phases: vec![
                CyclePhase {
                    name: "P1".into(),
                    skills: vec![first],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![second],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
            ],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: Some(CycleStateSchema {
                markers: vec![RuntimeMarkerDef {
                    id: "weapon".into(),
                    name: "Weapon".into(),
                    initial_value: "main".into(),
                    allowed_values: vec!["main".into(), "alt".into()],
                }],
                timers: vec![],
                counters: vec![],
            }),
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert_eq!(exec.runtime.marker("weapon"), Some("main"));
        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.runtime.marker("weapon"), Some("alt"));
        assert_eq!(exec.state.phase_index, 1);
        assert!(exec.tick(&mut ks, &|| false, 50));
        assert_eq!(ks.keys, vec!["f1", "f2"]);
    }

    #[test]
    fn test_counter_post_action_gates_next_phase_skill() {
        let mut first = make_slot("sk1", 1);
        first.post_actions = vec![RuntimeAction::IncrementCounter {
            counter_id: "main_wp2_count".into(),
            by: 1,
        }];

        let mut second = make_slot("sk2", 1);
        second.condition_expr = Some(json!({
            "type": "counter_ge",
            "counter_id": "main_wp2_count",
            "value": 1
        }));

        let config = CycleConfig {
            name: "test".into(),
            phases: vec![
                CyclePhase {
                    name: "P1".into(),
                    skills: vec![first],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![second],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
            ],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: Some(CycleStateSchema {
                markers: vec![],
                timers: vec![],
                counters: vec![RuntimeCounterDef {
                    id: "main_wp2_count".into(),
                    name: "Main WP2 Count".into(),
                    initial_value: 0,
                    reset_on_phase_entry: false,
                    reset_on_cycle_start: true,
                }],
            }),
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert_eq!(exec.runtime.counter("main_wp2_count"), Some(0));
        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.runtime.counter("main_wp2_count"), Some(1));
        assert_eq!(exec.state.phase_index, 1);
        assert!(exec.tick(&mut ks, &|| false, 50));
        assert_eq!(ks.keys, vec!["f1", "f2"]);
    }

    #[test]
    fn test_phase_transition_rule_jumps_to_named_phase() {
        let config = CycleConfig {
            name: "transition".into(),
            phases: vec![
                CyclePhase {
                    name: "P1".into(),
                    skills: vec![make_slot("sk1", 1)],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![PhaseTransitionRule {
                        label: "jump".into(),
                        condition_expr: Some(json!({"type": "const", "value": true})),
                        target_phase: "P3".into(),
                    }],
                    fallback_transition: Some(PhaseFallbackTransition::Next),
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![make_slot("sk2", 1)],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
                CyclePhase {
                    name: "P3".into(),
                    skills: vec![make_slot("sk3", 1)],
                    complete_when: "any_fired".into(),
                    entry_actions: vec![],
                    transition_rules: vec![],
                    fallback_transition: None,
                },
            ],
            assist_lanes: vec![],
            poll_interval_ms: 100,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![
            make_skill("sk1", "f1"),
            make_skill("sk2", "f2"),
            make_skill("sk3", "f3"),
        ];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.phase_index, 2);
        assert!(
            exec.log
                .iter()
                .any(|entry| entry.event == "phase_transition" && entry.reason == "rule:jump->P3")
        );
        assert!(exec.tick(&mut ks, &|| false, 1_000));
        assert_eq!(ks.keys, vec!["f1", "f3"]);
    }

    #[test]
    fn test_complete_expr_require_signal_times_out() {
        let mut slot = make_slot("sk1", 1);
        slot.complete_expr = Some(json!({"type": "const", "value": false}));
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.cast.readbar_ms = 100;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let cfg = SkillAttemptConfig {
            complete_policy: CompletePolicy::RequireSignal,
            complete_poll_ms: 25,
            complete_max_wait_factor: 1.0,
            ..Default::default()
        };
        let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 0);
        assert_eq!(exec.state.next_ready_ms, 25);
        assert!(exec.pending_attempt.is_some());

        assert!(!exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.total_executed, 0);

        assert!(exec.tick(&mut ks, &|| false, 100));
        assert_eq!(exec.state.total_executed, 1);
        assert_eq!(exec.state.last_outcome, "Failed");
        assert_eq!(exec.state.next_ready_ms, 150);
        assert!(exec.pending_attempt.is_none());
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.cast_started, 1);
        assert_eq!(runtime.success, 0);
        assert_eq!(runtime.fail, 1);
        assert_eq!(runtime.fail_by_reason.get("timeout"), Some(&1));
    }

    #[test]
    fn test_complete_expr_require_signal_succeeds() {
        let mut slot = make_slot("sk1", 1);
        slot.complete_expr = Some(json!({"type": "const", "value": true}));
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.cast.readbar_ms = 100;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let cfg = SkillAttemptConfig {
            complete_policy: CompletePolicy::RequireSignal,
            ..Default::default()
        };
        let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 1);
        assert_eq!(exec.state.last_outcome, "Success");
        assert_eq!(exec.state.next_ready_ms, 50);
        assert!(exec.pending_attempt.is_none());
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.cast_started, 1);
        assert_eq!(runtime.success, 1);
        assert_eq!(runtime.fail, 0);
    }

    #[test]
    fn test_runtime_metrics_after_not_ready() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![SkillSlot {
                    skill_id: "sk1".into(),
                    priority: 1,
                    label: String::new(),
                    condition_expr: Some(json!({"type": "const", "value": false})),
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
            }],
            assist_lanes: vec![],
            poll_interval_ms: 50,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1")];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(!exec.tick(&mut ks, &|| false, 0));
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.node_exec, 1);
        assert_eq!(runtime.ready_false, 1);
        assert_eq!(runtime.attempt_started, 0);
        assert_eq!(runtime.success, 0);
    }

    #[test]
    fn test_skill_cooldown_blocks_until_due() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "always".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.cooldown_ms = 100;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 1);
        assert!(!exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.total_executed, 1);
        assert!(exec.tick(&mut ks, &|| false, 100));
        assert_eq!(exec.state.total_executed, 2);
    }

    #[test]
    fn test_all_fired_respects_shots_per_cycle() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "all_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.shots_per_cycle = 2;
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.phase_index, 0);
        assert_eq!(exec.state.cycle_count, 0);
        assert!(exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.cycle_count, 1);
        assert_eq!(exec.state.total_executed, 2);
    }

    #[test]
    fn test_ammo_stage_pixel_blocks_when_no_charge_matches() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            assist_lanes: vec![],
            poll_interval_ms: 10,
            max_cycles: 0,
            state_schema: None,
        };
        let points = vec![];
        let mut skill = make_skill("sk1", "f1");
        skill.ammo_stages = vec![AmmoStagePixel {
            charges_left: 1,
            pixel: PixelSpec {
                monitor: "primary".into(),
                vx: 0,
                vy: 0,
                color: ColorRGB { r: 1, g: 2, b: 3 },
                tolerance: 0,
                sample: SampleConfig {
                    mode: "single".into(),
                    radius: 0,
                },
            },
        }];
        let skills = vec![skill];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let mut exec = CycleExecutor::new(
            &config,
            &points,
            &skills,
            &sampler,
            SkillAttemptConfig::default(),
        );
        let mut ks = DummyKeySender {
            keys: vec![],
            fail: false,
        };

        assert!(!exec.tick(&mut ks, &|| false, 0));
        assert_eq!(exec.state.total_executed, 0);
        let runtime = exec.runtime.skills.get("sk1").unwrap();
        assert_eq!(runtime.ready_false, 1);
    }
}
