use serde::{Deserialize, Serialize};

/// 单个技能配置
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Skill {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub trigger_key: String,
    pub cast: CastConfig,
    pub pixel: PixelSpec,
    pub note: String,
    pub game_id: u32,
    pub game_desc: String,
    pub icon_url: String,
    pub cooldown_ms: u32,
    pub radius: u32,
    pub shots_per_cycle: u32,
    pub ammo_stages: Vec<AmmoStagePixel>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ColorRGB {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SampleConfig {
    pub mode: String, // "single" | "mean_square"
    pub radius: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PixelSpec {
    pub monitor: String,
    pub vx: i32,
    pub vy: i32,
    pub color: ColorRGB,
    pub tolerance: u8,
    pub sample: SampleConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CastConfig {
    pub readbar_ms: u32,
    pub cooldown_ms: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AmmoStagePixel {
    pub charges_left: u32,
    pub pixel: PixelSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SkillsFile {
    pub schema_version: u32,
    pub skills: Vec<Skill>,
}
