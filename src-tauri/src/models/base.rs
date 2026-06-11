use serde::{Deserialize, Serialize};

use super::skill::ColorRGB;

/// 全局基础配置
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
    pub backup_on_save: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CastBarConfig {
    pub mode: String,
    pub point_id: String,
    pub tolerance: u8,
    pub poll_interval_ms: u32,
    pub max_wait_factor: f64,
    #[serde(default)]
    pub roi: CastBarRoiConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct CastBarRoiConfig {
    pub enabled: bool,
    pub monitor: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub baseline_color: ColorRGB,
    pub diff_threshold: u8,
    pub min_changed_ratio: f64,
    pub border_enabled: bool,
    pub border_color: ColorRGB,
    pub border_tolerance: u8,
    pub min_border_match_ratio: f64,
    pub confirm_frames: u32,
}

impl Default for CastBarRoiConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            monitor: "primary".into(),
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            baseline_color: ColorRGB { r: 0, g: 0, b: 0 },
            diff_threshold: 18,
            min_changed_ratio: 0.08,
            border_enabled: false,
            border_color: ColorRGB { r: 0, g: 0, b: 0 },
            border_tolerance: 24,
            min_border_match_ratio: 0.2,
            confirm_frames: 2,
        }
    }
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
