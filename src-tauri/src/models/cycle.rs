use serde::{Deserialize, Serialize};

/// 阶段循环配置（对齐 python-legacy rotation_editor/core/models/cycle.py）
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CycleConfig {
    pub name: String,
    pub phases: Vec<CyclePhase>,
    pub poll_interval_ms: u32,
    pub max_cycles: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CyclePhase {
    pub name: String,
    pub skills: Vec<SkillSlot>,
    pub complete_when: String, // "all_fired" | "any_fired" | "always"
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SkillSlot {
    pub skill_id: String,
    pub priority: u32,
    pub label: String,
    #[serde(default)]
    pub condition_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub start_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub complete_expr: Option<serde_json::Value>,
    #[serde(default)]
    pub override_cast_ms: Option<u32>,
}
