//! Phase and priority cycle executor.
//!
//! Execution model:
//! 1. Keep the active phase index and fired skill sets.
//! 2. On each tick, scan the active phase by priority.
//! 3. Start the first ready skill attempt.
//! 4. Advance pending attempts across later ticks without blocking.
//! 5. Advance or reset phases after attempts finish.

use crate::ast::compiler::compile_expr_json;
use crate::ast::evaluator::{EvalContext, PixelSampler, evaluate};
use crate::ast::nodes::Expr;
use crate::engine::runtime_state::RuntimeState;
use crate::engine::skill_attempt::{
    Advance, AttemptEvent, CompletePolicy, ExecutionResult, KeySender, SkillAttemptConfig,
};
use crate::models::cycle::{CycleConfig, CyclePhase, SkillSlot};
use crate::models::point::Point;
use crate::models::skill::Skill;
use std::collections::HashSet;

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
    pub total_executed: u32,
    pub last_skill_id: String,
    pub last_outcome: String,
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
    pub attempt_cfg: SkillAttemptConfig,
    pub state: CycleExecState,
    pub runtime: RuntimeState,
    pub log: Vec<CycleExecLogEntry>,
    pending_attempt: Option<PendingAttempt>,

    // Compiled condition cache: skill_id -> condition expression.
    pub expr_cache: Vec<(String, Option<Expr>)>,
}

#[derive(Debug, Clone)]
struct PendingAttempt {
    phase_index: usize,
    phase_name: String,
    skill_id: String,
    readbar_ms: u32,
    start_expr: Expr,
    complete_expr: Option<Expr>,
    stage: PendingAttemptStage,
    retries_left: u32,
    deadline_ms: u64,
    next_poll_ms: u64,
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

        Self {
            config,
            points,
            skills,
            sampler,
            attempt_cfg,
            state: CycleExecState::default(),
            runtime: RuntimeState::new(),
            log: Vec::new(),
            pending_attempt: None,
            expr_cache,
        }
    }

    /// Advance the cycle executor by one scheduler tick.
    pub fn tick(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
    ) -> bool {
        if stopped() {
            if let Some(pending) = self.pending_attempt.take() {
                self.apply_attempt_event(AttemptEvent::Stopped {
                    skill_id: pending.skill_id,
                });
            }
            return false;
        }

        if now_ms < self.state.next_ready_ms {
            return false;
        }

        if let Some(pending) = self.pending_attempt.take() {
            return self.advance_pending_attempt(key_sender, stopped, now_ms, pending);
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
        let mut sorted_slots: Vec<&SkillSlot> = phase.skills.iter().collect();
        sorted_slots.sort_by_key(|slot| slot.priority);

        for slot in &sorted_slots {
            let sid = slot.skill_id.trim();
            if sid.is_empty() {
                continue;
            }

            if self.state.fired_in_phase.contains(sid) && phase.complete_when != "always" {
                continue;
            }

            self.runtime.mark_node_exec(sid);

            let (ready, cond_reason) = self.check_skill_ready(slot);
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

            if let Some(execution) =
                self.begin_skill_attempt(key_sender, slot, stopped, now_ms, phase_idx, phase)
            {
                self.finish_skill_attempt(phase_idx, phase, sid, execution, now_ms);
            }

            return true;
        }

        false
    }

    fn check_skill_ready(&self, slot: &SkillSlot) -> (bool, String) {
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

        let expr = self
            .expr_cache
            .iter()
            .find(|(id, _)| id.as_str() == sid)
            .and_then(|(_, e)| e.as_ref());

        if let Some(e) = expr {
            let ctx = EvalContext {
                points: self.points,
                skills: self.skills,
                sampler: self.sampler,
                metrics: Some(&self.runtime),
                baseline: None,
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

    fn begin_skill_attempt(
        &mut self,
        key_sender: &mut dyn KeySender,
        slot: &SkillSlot,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
        phase_index: usize,
        phase: &CyclePhase,
    ) -> Option<ExecutionResult> {
        let sid = slot.skill_id.trim().to_string();
        let Some(skill) = self.skills.iter().find(|skill| skill.id.as_str() == sid) else {
            return Some(ExecutionResult::failed(
                Advance::Advance,
                self.attempt_cfg.poll_not_ready_ms,
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
                Advance::Advance,
                self.attempt_cfg.poll_not_ready_ms,
                "send_key_failed",
            ));
        }

        self.apply_attempt_event(AttemptEvent::KeySentOk {
            skill_id: sid.clone(),
        });

        self.pending_attempt = Some(PendingAttempt {
            phase_index,
            phase_name: phase.name.clone(),
            skill_id: sid,
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
            stage: PendingAttemptStage::StartWait,
            retries_left: self.attempt_cfg.max_retries,
            deadline_ms: now_ms.saturating_add(u64::from(self.attempt_cfg.start_timeout_ms)),
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
                let phase = self.config.phases.get(pending.phase_index).cloned();
                if let Some(phase) = phase {
                    self.finish_skill_attempt(
                        pending.phase_index,
                        &phase,
                        &pending.skill_id,
                        execution,
                        now_ms,
                    );
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
            pending.deadline_ms = self.complete_deadline_ms(now_ms, pending.readbar_ms);
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
                    Advance::Advance,
                    self.attempt_cfg.poll_not_ready_ms,
                    "no_cast_start",
                ));
            }
            pending.stage = PendingAttemptStage::RetryDelay;
            pending.next_poll_ms = now_ms.saturating_add(u64::from(self.attempt_cfg.retry_gap_ms));
            return None;
        }

        pending.next_poll_ms = now_ms
            .saturating_add(u64::from(self.attempt_cfg.start_poll_ms.max(1)))
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
                    Advance::Advance,
                    self.attempt_cfg.poll_not_ready_ms,
                    "send_key_failed_retry",
                ));
            }
            self.apply_attempt_event(AttemptEvent::KeySentOk {
                skill_id: pending.skill_id.clone(),
            });
            pending.retries_left = pending.retries_left.saturating_sub(1);
            pending.stage = PendingAttemptStage::StartWait;
            pending.deadline_ms =
                now_ms.saturating_add(u64::from(self.attempt_cfg.start_timeout_ms));
            pending.next_poll_ms = now_ms;
            return self.advance_start_wait(key_sender, now_ms, pending);
        }

        Some(ExecutionResult::failed(
            Advance::Advance,
            self.attempt_cfg.poll_not_ready_ms,
            "skill_missing",
        ))
    }

    fn advance_complete_wait(
        &mut self,
        now_ms: u64,
        pending: &mut PendingAttempt,
    ) -> Option<ExecutionResult> {
        match self.attempt_cfg.complete_policy {
            CompletePolicy::AssumeSuccess => {
                if pending.readbar_ms == 0 || now_ms >= pending.deadline_ms {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        self.attempt_cfg.default_gap_ms,
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
                        self.attempt_cfg.default_gap_ms,
                        "success",
                    ));
                }
                if now_ms >= pending.deadline_ms {
                    self.apply_attempt_event(AttemptEvent::Failed {
                        skill_id: pending.skill_id.clone(),
                        reason: "timeout".into(),
                    });
                    return Some(ExecutionResult::failed(
                        Advance::Advance,
                        self.attempt_cfg.poll_not_ready_ms,
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
                        self.attempt_cfg.default_gap_ms,
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
                        Advance::Advance,
                        self.attempt_cfg.poll_not_ready_ms,
                        "complete_signal_missing",
                    ));
                };

                if self.evaluate_expr(expr) {
                    self.apply_attempt_event(AttemptEvent::Succeeded {
                        skill_id: pending.skill_id.clone(),
                    });
                    return Some(ExecutionResult::success(
                        self.attempt_cfg.default_gap_ms,
                        "success",
                    ));
                }

                if now_ms >= pending.deadline_ms {
                    if self.attempt_cfg.complete_policy == CompletePolicy::HybridAssume {
                        self.apply_attempt_event(AttemptEvent::Succeeded {
                            skill_id: pending.skill_id.clone(),
                        });
                        return Some(ExecutionResult::success(
                            self.attempt_cfg.default_gap_ms,
                            "hybrid_assume_timeout",
                        ));
                    }
                    self.apply_attempt_event(AttemptEvent::Failed {
                        skill_id: pending.skill_id.clone(),
                        reason: "timeout".into(),
                    });
                    return Some(ExecutionResult::failed(
                        Advance::Advance,
                        self.attempt_cfg.poll_not_ready_ms,
                        "timeout",
                    ));
                }
            }
        }

        pending.next_poll_ms = now_ms
            .saturating_add(u64::from(self.attempt_cfg.complete_poll_ms.max(1)))
            .min(pending.deadline_ms);
        None
    }

    fn finish_skill_attempt(
        &mut self,
        phase_idx: usize,
        phase: &CyclePhase,
        skill_id: &str,
        execution: ExecutionResult,
        now_ms: u64,
    ) {
        let outcome = format!("{:?}", execution.outcome);
        self.state.next_ready_ms = now_ms.saturating_add(u64::from(execution.next_delay_ms));
        self.state.fired_in_phase.insert(skill_id.to_string());
        self.state.fired_in_cycle.insert(skill_id.to_string());
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

        if self.is_phase_complete(phase) {
            self.on_phase_complete(phase_idx, phase);
            if self.state.phase_index >= self.config.phases.len() {
                self.on_cycle_reset();
            }
        }
    }

    fn complete_deadline_ms(&self, now_ms: u64, readbar_ms: u32) -> u64 {
        if readbar_ms == 0 {
            return now_ms;
        }
        let wait_ms = match self.attempt_cfg.complete_policy {
            CompletePolicy::AssumeSuccess => readbar_ms,
            _ => (readbar_ms as f64 * self.attempt_cfg.complete_max_wait_factor).max(1.0) as u32,
        };
        now_ms.saturating_add(u64::from(wait_ms))
    }

    fn evaluate_expr(&self, expr: &Expr) -> bool {
        let ctx = EvalContext {
            points: self.points,
            skills: self.skills,
            sampler: self.sampler,
            metrics: Some(&self.runtime),
            baseline: None,
        };
        evaluate(expr, &ctx).is_true()
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
                    || !self.check_skill_ready(slot).0
            }),
            _ => {
                let all_ids: HashSet<&str> = phase
                    .skills
                    .iter()
                    .map(|s| s.skill_id.as_str())
                    .filter(|s| !s.is_empty())
                    .collect();
                all_ids
                    .iter()
                    .all(|id| self.state.fired_in_phase.contains(*id))
            }
        }
    }

    fn on_phase_complete(&mut self, phase_idx: usize, _phase: &CyclePhase) {
        self.state.phase_index = phase_idx + 1;
        self.state.fired_in_phase.clear();
        // Outer tick code records phase-level logs.
    }

    fn on_cycle_reset(&mut self) {
        self.state.cycle_count += 1;
        self.state.phase_index = 0;
        self.state.fired_in_phase.clear();
        self.state.fired_in_cycle.clear();
        // Runtime metrics are cumulative and are not reset per cycle.
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

// ===========================================================================
// 娴嬭瘯
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::evaluator::PixelSampler;
    use crate::models::cycle::{CyclePhase, SkillSlot};
    use crate::models::skill::{ColorRGB, PixelSpec, SampleConfig, Skill};
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
    fn test_single_phase_single_skill() {
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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

        // tick 1: 搴旇鎵ц skA (priority 1)
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
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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
                }],
                complete_when: "any_fired".into(),
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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
                },
                CyclePhase {
                    name: "P2".into(),
                    skills: vec![make_slot("skC", 1)],
                    complete_when: "any_fired".into(),
                },
            ],
            poll_interval_ms: 50,
            max_cycles: 0,
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
        assert_eq!(exec.state.phase_index, 0); // 杩樺湪 P1 (all_fired 鏈叏閮ㄥ畬鎴?

        // tick 2: skB (priority 2, skA 宸插畬鎴?
        assert!(exec.tick(&mut ks, &|| false, 50));
        assert_eq!(exec.state.phase_index, 1); // P1 瀹屾垚 鈫?P2

        // tick 3: skC (P2)
        assert!(exec.tick(&mut ks, &|| false, 100));
        // P2 瀹屾垚 鈫?cycle reset 鈫?鍥炲埌 P1
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
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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
            }],
            poll_interval_ms: 10,
            max_cycles: 0,
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
            }],
            poll_interval_ms: 10,
            max_cycles: 0,
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
    fn test_complete_expr_require_signal_times_out() {
        let mut slot = make_slot("sk1", 1);
        slot.complete_expr = Some(json!({"type": "const", "value": false}));
        let config = CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
            }],
            poll_interval_ms: 10,
            max_cycles: 0,
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
            }],
            poll_interval_ms: 10,
            max_cycles: 0,
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
                }],
                complete_when: "any_fired".into(),
            }],
            poll_interval_ms: 50,
            max_cycles: 0,
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
}
