use serde::{Deserialize, Serialize};

use super::base::BaseConfig;
use super::cycle::CycleConfig;
use super::point::PointsFile;
use super::skill::SkillsFile;

/// Profile 聚合根（对齐 python-legacy core/domain/profile.py）
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Profile {
    pub schema_version: u32,
    pub meta: ProfileMeta,
    pub base: BaseConfig,
    pub skills: SkillsFile,
    pub points: PointsFile,
    pub rotations: Vec<CycleConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProfileMeta {
    pub profile_id: String,
    pub profile_name: String,
    pub created_at: String,
    pub updated_at: String,
    pub description: String,
}
