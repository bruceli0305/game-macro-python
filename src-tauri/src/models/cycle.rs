use serde::{Deserialize, Serialize};

/// 阶段循环配置
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CycleConfig {
    pub name: String,
    pub phases: Vec<CyclePhase>,
    #[serde(default)]
    pub observer_lanes: Vec<ObserverLaneConfig>,
    #[serde(default)]
    pub assist_lanes: Vec<AssistLaneConfig>,
    pub poll_interval_ms: u32,
    pub max_cycles: u32,
    #[serde(default)]
    pub state_schema: Option<CycleStateSchema>,
}

/// Background observer lane that evaluates conditions and applies runtime actions only.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ObserverLaneConfig {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub check_interval_ms: u32,
    #[serde(default)]
    pub actions: Vec<ObserverActionSlot>,
}

/// Condition-only action slot used by observer lanes.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ObserverActionSlot {
    pub id: String,
    pub label: String,
    pub priority: u32,
    #[serde(default)]
    pub condition_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub actions: Vec<RuntimeAction>,
}

/// Background assist lane configuration evaluated by the cycle scheduler.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AssistLaneConfig {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub check_interval_ms: u32,
    #[serde(default)]
    pub interrupt_policy: AssistInterruptPolicy,
    #[serde(default)]
    pub skills: Vec<SkillSlot>,
}

/// Policy describing when an assist lane may attempt a skill relative to the main lane.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum AssistInterruptPolicy {
    /// Only check assist skills when the main lane is idle between attempts.
    #[default]
    IdleOnly,
    /// Allow assist skills while the main lane is waiting for a skill completion signal.
    CompleteWait,
    /// Allow assist skills during any main-lane wait state.
    AnyWait,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CyclePhase {
    pub name: String,
    pub skills: Vec<SkillSlot>,
    pub complete_when: String, // "all_fired" | "any_fired" | "always"
    #[serde(default)]
    pub entry_actions: Vec<RuntimeAction>,
    #[serde(default)]
    pub transition_rules: Vec<PhaseTransitionRule>,
    #[serde(default)]
    pub fallback_transition: Option<PhaseFallbackTransition>,
}

/// Conditional jump evaluated after a phase completes.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PhaseTransitionRule {
    pub label: String,
    #[serde(default)]
    pub condition_expr: Option<serde_json::Value>,
    pub target_phase: String,
}

/// Fallback jump used when no phase transition rule matches.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum PhaseFallbackTransition {
    #[serde(rename = "stay")]
    Stay,
    #[serde(rename = "next")]
    Next,
    #[serde(rename = "phase")]
    Phase { target_phase: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SkillSlot {
    pub skill_id: String,
    pub priority: u32,
    pub label: String,
    #[serde(default)]
    pub slot_role: SkillSlotRole,
    #[serde(default)]
    pub condition_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub readiness_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub readiness_policy: ReadinessPolicy,
    #[serde(default)]
    pub start_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub complete_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub override_cast_ms: Option<u32>,
    #[serde(default)]
    pub protected_release: bool,
    #[serde(default)]
    pub attempt_policy: Option<AttemptPolicy>,
    #[serde(default)]
    pub post_actions: Vec<RuntimeAction>,
}

/// Semantic role of a skill slot inside a phase or assist lane.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SkillSlotRole {
    /// A phase-owned action required for the phase's intended rotation segment.
    #[default]
    Mandatory,
    /// A high-value action that can be inserted when available.
    Priority,
    /// A low-value filler action used only when stronger actions are unavailable.
    Filler,
}

/// How a skill slot should treat its readiness expression.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReadinessPolicy {
    /// Readiness must be true before a key attempt starts.
    #[default]
    Required,
    /// Readiness is diagnostic only; hard conditions decide candidate eligibility.
    Advisory,
}

/// Per-slot skill-attempt policy.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttemptPolicy {
    pub max_attempts: u32,
    pub start_timeout_ms: u32,
    pub complete_timeout_ms: u32,
    pub retry_delay_ms: u32,
    pub failure_policy: String,
    pub complete_fallback: String,
}

/// Runtime state declarations owned by a cycle.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CycleStateSchema {
    #[serde(default)]
    pub markers: Vec<RuntimeMarkerDef>,
    #[serde(default)]
    pub timers: Vec<RuntimeTimerDef>,
    #[serde(default)]
    pub counters: Vec<RuntimeCounterDef>,
}

/// Named marker available to AST conditions and runtime actions.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuntimeMarkerDef {
    pub id: String,
    pub name: String,
    pub initial_value: String,
    #[serde(default)]
    pub allowed_values: Vec<String>,
}

/// Named timer available to AST conditions and runtime actions.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuntimeTimerDef {
    pub id: String,
    pub name: String,
    pub reset_on_cycle_start: bool,
}

/// Named counter available to AST conditions and runtime actions.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RuntimeCounterDef {
    pub id: String,
    pub name: String,
    pub initial_value: i64,
    pub reset_on_phase_entry: bool,
    pub reset_on_cycle_start: bool,
}

/// Runtime side effects applied by phases or successful skill slots.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum RuntimeAction {
    #[serde(rename = "set_marker")]
    SetMarker { marker_id: String, value: String },
    #[serde(rename = "clear_marker")]
    ClearMarker { marker_id: String },
    #[serde(rename = "record_timer")]
    RecordTimer { timer_id: String },
    #[serde(rename = "reset_timer")]
    ResetTimer { timer_id: String },
    #[serde(rename = "increment_counter")]
    IncrementCounter { counter_id: String, by: i64 },
    #[serde(rename = "set_counter")]
    SetCounter { counter_id: String, value: i64 },
    #[serde(rename = "reset_counter")]
    ResetCounter { counter_id: String },
}

#[cfg(test)]
mod tests {
    use super::{ReadinessPolicy, SkillSlot, SkillSlotRole};

    #[test]
    fn skill_slot_role_defaults_to_mandatory_for_legacy_json() {
        let slot: SkillSlot = serde_json::from_value(serde_json::json!({
            "skill_id": "skill-1",
            "priority": 1,
            "label": "legacy slot"
        }))
        .expect("legacy skill slot should deserialize");

        assert_eq!(slot.slot_role, SkillSlotRole::Mandatory);
        assert_eq!(slot.readiness_policy, ReadinessPolicy::Required);
        assert!(slot.readiness_expr.is_none());
    }

    #[test]
    fn skill_slot_role_serializes_as_snake_case() {
        let slot = SkillSlot {
            skill_id: "skill-1".into(),
            priority: 1,
            label: "filler".into(),
            slot_role: SkillSlotRole::Filler,
            ..SkillSlot::default()
        };
        let value = serde_json::to_value(slot).expect("skill slot should serialize");

        assert_eq!(value["slot_role"], "filler");
    }

    #[test]
    fn readiness_policy_serializes_as_snake_case() {
        let slot = SkillSlot {
            skill_id: "skill-1".into(),
            priority: 1,
            label: "advisory".into(),
            readiness_policy: ReadinessPolicy::Advisory,
            ..SkillSlot::default()
        };
        let value = serde_json::to_value(slot).expect("skill slot should serialize");

        assert_eq!(value["readiness_policy"], "advisory");
    }
}
