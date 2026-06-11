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
use crate::engine::skill_attempt::SkillAttemptConfig;
use crate::models::cycle::CycleConfig;
use crate::models::point::Point;
use crate::models::skill::Skill;
use std::collections::HashMap;

pub(crate) use crate::engine::cycle_state::CycleLogEvent;
pub use crate::engine::cycle_state::{CycleExecLogEntry, CycleExecState};
// Re-exported for tests that import the executor module with `super::*`.
#[cfg(test)]
pub(crate) use crate::engine::skill_attempt::{CompletePolicy, KeySender};

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
    CompiledSlotExprs, ObserverActionExprKey, PendingAttempt, SlotExprKey,
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
}

// ===========================================================================
// Tests.
// ===========================================================================

#[cfg(test)]
#[path = "cycle_executor_tests.rs"]
mod tests;
