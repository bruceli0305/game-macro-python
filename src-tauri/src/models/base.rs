use serde::{Deserialize, Serialize};

/// 全局基础配置（对齐 python-legacy core/models/base.py）
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BaseConfig {
    pub schema_version: u32,
    pub ui: UiConfig,
    pub capture: CaptureConfig,
    pub pick: PickConfig,
    pub io: IoConfig,
    pub cast_bar: CastBarConfig,
    pub exec: ExecConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UiConfig {
    pub theme: String, // "darkly" | "light"
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CaptureConfig {
    pub monitor_policy: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PickConfig {
    pub confirm_hotkey: String,
    pub mouse_avoid: bool,
    pub mouse_avoid_offset_y: i32,
    pub mouse_avoid_settle_ms: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct IoConfig {
    pub auto_save: bool,
    pub backup_on_save: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CastBarConfig {
    pub mode: String,
    pub point_id: String,
    pub tolerance: u8,
    pub poll_interval_ms: u32,
    pub max_wait_factor: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ExecConfig {
    pub enabled: bool,
    pub toggle_hotkey: String,
    pub default_skill_gap_ms: u32,
    pub poll_not_ready_ms: u32,
    pub max_retries: u32,
    pub retry_gap_ms: u32,
}
