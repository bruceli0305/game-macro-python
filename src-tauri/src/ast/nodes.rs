use serde::{Deserialize, Serialize};

/// AST 条件表达式节点
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum Expr {
    #[serde(rename = "and")]
    And { children: Vec<Expr> },
    #[serde(rename = "or")]
    Or { children: Vec<Expr> },
    #[serde(rename = "not")]
    Not { child: Box<Expr> },
    #[serde(rename = "const")]
    Const { value: bool },
    #[serde(rename = "pixel_point")]
    PixelMatchPoint { point_id: String, tolerance: u8 },
    #[serde(rename = "pixel_point_not_match")]
    PixelPointNotMatch { point_id: String, tolerance: u8 },
    #[serde(rename = "pixel_point_black")]
    PixelPointBlack { point_id: String, tolerance: u8 },
    #[serde(rename = "pixel_point_not_black")]
    PixelPointNotBlack { point_id: String, tolerance: u8 },
    #[serde(rename = "pixel_point_nearest")]
    PixelPointNearest {
        expected_point_id: String,
        candidate_point_ids: Vec<String>,
        max_delta: u8,
        min_margin: u8,
    },
    #[serde(rename = "pixel_skill")]
    PixelMatchSkill { skill_id: String, tolerance: u8 },
    #[serde(rename = "pixel_skill_not_match")]
    PixelSkillNotMatch { skill_id: String, tolerance: u8 },
    #[serde(rename = "pixel_skill_black")]
    PixelSkillBlack { skill_id: String, tolerance: u8 },
    #[serde(rename = "pixel_skill_not_black")]
    PixelSkillNotBlack { skill_id: String, tolerance: u8 },
    #[serde(rename = "cast_bar_changed")]
    CastBarChanged { point_id: String, tolerance: u8 },
    #[serde(rename = "cast_bar_roi_changed")]
    CastBarRoiChanged,
    #[serde(rename = "cast_bar_roi_border_visible")]
    CastBarRoiBorderVisible,
    #[serde(rename = "cast_bar_roi_gone")]
    CastBarRoiGone,
    #[serde(rename = "skill_metric_ge")]
    SkillMetricGE {
        skill_id: String,
        metric: SkillMetric,
        count: u32,
    },
    #[serde(rename = "marker_eq")]
    MarkerEq { marker_id: String, value: String },
    #[serde(rename = "marker_ne")]
    MarkerNe { marker_id: String, value: String },
    #[serde(rename = "timer_elapsed_ge")]
    TimerElapsedGE { timer_id: String, ms: u64 },
    #[serde(rename = "timer_elapsed_lt")]
    TimerElapsedLT { timer_id: String, ms: u64 },
    #[serde(rename = "counter_ge")]
    CounterGE { counter_id: String, value: i64 },
    #[serde(rename = "counter_eq")]
    CounterEq { counter_id: String, value: i64 },
    #[serde(rename = "counter_gt")]
    CounterGT { counter_id: String, value: i64 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SkillMetric {
    #[serde(rename = "success")]
    Success,
    #[serde(rename = "attempt_started")]
    AttemptStarted,
    #[serde(rename = "key_sent_ok")]
    KeySentOk,
    #[serde(rename = "cast_started")]
    CastStarted,
    #[serde(rename = "fail")]
    Fail,
}
