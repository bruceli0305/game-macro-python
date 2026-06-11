//! Precompiled runtime configuration for the cycle executor.
//!
//! Holds compile-time expression caches — slot conditions, transition rules,
//! and observer action conditions — plus the pending-attempt state machine
//! types used by the attempt tracker.

use std::collections::HashMap;

use crate::ast::compiler::compile_expr_json;
use crate::ast::nodes::Expr;
use crate::engine::skill_attempt::SkillAttemptConfig;
use crate::models::cycle::{CycleConfig, ObserverActionSlot, RuntimeAction, SkillSlot};

// ---------------------------------------------------------------------------
// Precompiled slot expressions.
// ---------------------------------------------------------------------------

/// Precompiled condition/readiness/start/complete expressions for a single skill slot.
#[derive(Debug, Clone)]
pub(crate) struct CompiledSlotExprs {
    pub(crate) condition_expr: Option<Expr>,
    pub(crate) readiness_expr: Option<Expr>,
    pub(crate) start_expr: Option<Expr>,
    pub(crate) complete_expr: Option<Expr>,
}

// ---------------------------------------------------------------------------
// Pending attempt state machine types.
// ---------------------------------------------------------------------------

/// In-flight skill attempt tracking state.
#[derive(Debug, Clone)]
pub(crate) struct PendingAttempt {
    pub(crate) context: AttemptContext,
    pub(crate) skill_id: String,
    pub(crate) post_actions: Vec<RuntimeAction>,
    pub(crate) readbar_ms: u32,
    pub(crate) start_expr: Expr,
    pub(crate) complete_expr: Option<Expr>,
    pub(crate) protected_release: bool,
    pub(crate) attempt_cfg: SkillAttemptConfig,
    pub(crate) stage: PendingAttemptStage,
    pub(crate) retries_left: u32,
    pub(crate) deadline_ms: u64,
    pub(crate) next_poll_ms: u64,
}

#[derive(Debug, Clone)]
pub(crate) enum AttemptContext {
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
pub(crate) enum PendingAttemptStage {
    StartWait,
    RetryDelay,
    CompleteWait,
}

// ---------------------------------------------------------------------------
// Cache building — pure functions, no executor dependency.
// ---------------------------------------------------------------------------

/// Build a cache of precompiled expressions for every skill slot across
/// all phases and assist lanes.
pub(crate) fn build_slot_expr_cache(config: &CycleConfig) -> HashMap<usize, CompiledSlotExprs> {
    let mut cache = HashMap::new();
    for phase in &config.phases {
        for slot in &phase.skills {
            cache.insert(slot_cache_key(slot), compile_slot_exprs(slot));
        }
    }
    for lane in &config.assist_lanes {
        for slot in &lane.skills {
            cache.insert(slot_cache_key(slot), compile_slot_exprs(slot));
        }
    }
    cache
}

/// Build a cache of precompiled observer action conditions.
pub(crate) fn build_observer_action_expr_cache(
    config: &CycleConfig,
) -> HashMap<usize, Option<Expr>> {
    let mut cache = HashMap::new();
    for lane in &config.observer_lanes {
        for action in &lane.actions {
            cache.insert(
                observer_action_cache_key(action),
                action
                    .condition_expr
                    .as_ref()
                    .and_then(|value| compile_expr_json(value, "$.condition_expr").expr),
            );
        }
    }
    cache
}

/// Build a precompiled transition rule expression cache, indexed by
/// `(phase_index, rule_index)`.
pub(crate) fn build_transition_rule_expr_cache(config: &CycleConfig) -> Vec<Vec<Option<Expr>>> {
    config
        .phases
        .iter()
        .map(|phase| {
            phase
                .transition_rules
                .iter()
                .map(|rule| {
                    rule.condition_expr
                        .as_ref()
                        .and_then(|value| compile_expr_json(value, "$.condition_expr").expr)
                })
                .collect()
        })
        .collect()
}

/// Pointer-based cache key for a skill slot — unique per allocation.
pub(crate) fn slot_cache_key(slot: &SkillSlot) -> usize {
    slot as *const SkillSlot as usize
}

/// Pointer-based cache key for an observer action slot.
pub(crate) fn observer_action_cache_key(slot: &ObserverActionSlot) -> usize {
    slot as *const ObserverActionSlot as usize
}

// ---------------------------------------------------------------------------
// Internal helpers.
// ---------------------------------------------------------------------------

fn compile_slot_exprs(slot: &SkillSlot) -> CompiledSlotExprs {
    CompiledSlotExprs {
        condition_expr: slot
            .condition_expr
            .as_ref()
            .and_then(|value| compile_expr_json(value, "$.condition_expr").expr),
        readiness_expr: slot
            .readiness_expr
            .as_ref()
            .and_then(|value| compile_expr_json(value, "$.readiness_expr").expr),
        start_expr: slot
            .start_expr
            .as_ref()
            .and_then(|value| compile_expr_json(value, "$.start_expr").expr),
        complete_expr: slot
            .complete_expr
            .as_ref()
            .and_then(|value| compile_expr_json(value, "$.complete_expr").expr),
    }
}
