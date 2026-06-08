use serde::{Deserialize, Serialize};

use super::skill::{ColorRGB, SampleConfig};

/// 取色点位（对齐 python-legacy core/models/point.py）
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Point {
    pub id: String,
    pub name: String,
    pub monitor: String,
    pub vx: i32,
    pub vy: i32,
    pub color: ColorRGB,
    pub tolerance: u8,
    pub sample: SampleConfig,
    pub captured_at: String,
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PointsFile {
    pub schema_version: u32,
    pub points: Vec<Point>,
}
