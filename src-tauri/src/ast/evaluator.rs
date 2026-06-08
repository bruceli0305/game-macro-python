use super::nodes::{Expr, SkillMetric};
use crate::models::point::Point;
use crate::models::skill::Skill;

// ---------------------------------------------------------------------------
// Traits — 抽象运行时依赖，便于单元测试
// ---------------------------------------------------------------------------

/// 像素采样接口
pub trait PixelSampler: Send + Sync {
    /// 在虚拟屏幕绝对坐标 (x_abs, y_abs) 采样 RGB，失败返回 None
    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        sample_mode: &str,
        sample_radius: u8,
    ) -> Option<(u8, u8, u8)>;
}

/// 技能指标读取接口
pub trait MetricProvider: Send + Sync {
    fn get_metric(&self, skill_id: &str, metric: &SkillMetric) -> Option<u32>;
}

/// 基线 RGB 读取接口（用于 CastBarChanged）
pub trait BaselineProvider: Send + Sync {
    fn get_point_baseline_rgb(&self, point_id: &str) -> Option<(u8, u8, u8)>;
}

// ---------------------------------------------------------------------------
// TriBool — 三值逻辑
// ---------------------------------------------------------------------------

/// 三值逻辑求值结果
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TriBool {
    True,
    False(String),
    Unknown(String),
}

impl TriBool {
    pub fn is_true(&self) -> bool {
        matches!(self, TriBool::True)
    }

    pub fn is_false(&self) -> bool {
        matches!(self, TriBool::False(_))
    }

    pub fn is_unknown(&self) -> bool {
        matches!(self, TriBool::Unknown(_))
    }
}

// ---------------------------------------------------------------------------
// EvalContext
// ---------------------------------------------------------------------------

/// 求值上下文：包含配置数据 + 运行时采样接口
pub struct EvalContext<'a> {
    /// point_id → Point（用于解析目标颜色/坐标/容差）
    pub points: &'a [Point],
    /// skill_id → Skill（用于解析技能像素/坐标/容差）
    pub skills: &'a [Skill],
    /// 像素采样器（截屏或测试替身）
    pub sampler: &'a dyn PixelSampler,
    /// 技能指标（可选）
    pub metrics: Option<&'a dyn MetricProvider>,
    /// 基线 RGB（可选，用于 CastBarChanged）
    pub baseline: Option<&'a dyn BaselineProvider>,
}

// ---------------------------------------------------------------------------
// evaluate — 递归求值入口
// ---------------------------------------------------------------------------

/// 三值逻辑求值（Kleene 逻辑）
pub fn evaluate(expr: &Expr, ctx: &EvalContext) -> TriBool {
    match expr {
        Expr::And { children } => eval_and(children, ctx),
        Expr::Or { children } => eval_or(children, ctx),
        Expr::Not { child } => eval_not(child, ctx),
        Expr::Const { value } => {
            if *value {
                TriBool::True
            } else {
                TriBool::False("const(false)".into())
            }
        }
        Expr::PixelMatchPoint {
            point_id,
            tolerance,
        } => eval_pixel_match_point(point_id, *tolerance, ctx),
        Expr::PixelMatchSkill {
            skill_id,
            tolerance,
        } => eval_pixel_match_skill(skill_id, *tolerance, ctx),
        Expr::CastBarChanged {
            point_id,
            tolerance,
        } => eval_cast_bar_changed(point_id, *tolerance, ctx),
        Expr::SkillMetricGE {
            skill_id,
            metric,
            count,
        } => eval_skill_metric_ge(skill_id, metric, *count, ctx),
    }
}

// ---------------------------------------------------------------------------
// Kleene 逻辑
// ---------------------------------------------------------------------------

fn eval_and(children: &[Expr], ctx: &EvalContext) -> TriBool {
    let mut saw_unknown: Option<TriBool> = None;
    for c in children {
        match evaluate(c, ctx) {
            r @ TriBool::False(_) => return r,
            r @ TriBool::Unknown(_) if saw_unknown.is_none() => saw_unknown = Some(r),
            _ => {}
        }
    }
    saw_unknown.unwrap_or(TriBool::True)
}

fn eval_or(children: &[Expr], ctx: &EvalContext) -> TriBool {
    let mut saw_unknown: Option<TriBool> = None;
    for c in children {
        match evaluate(c, ctx) {
            r @ TriBool::True => return r,
            r @ TriBool::Unknown(_) if saw_unknown.is_none() => saw_unknown = Some(r),
            _ => {}
        }
    }
    saw_unknown.unwrap_or(TriBool::False("or_all_false".into()))
}

fn eval_not(child: &Expr, ctx: &EvalContext) -> TriBool {
    match evaluate(child, ctx) {
        TriBool::True => TriBool::False("not(true)".into()),
        TriBool::False(_) => TriBool::True,
        r @ TriBool::Unknown(_) => r,
    }
}

// ---------------------------------------------------------------------------
// 原子求值
// ---------------------------------------------------------------------------

fn eval_pixel_match_point(point_id: &str, tolerance: u8, ctx: &EvalContext) -> TriBool {
    let pid = point_id.trim();
    if pid.is_empty() {
        return TriBool::Unknown("point_id_empty".into());
    }

    let p = ctx.points.iter().find(|p| p.id.as_str() == pid);
    let p = match p {
        Some(p) => p,
        None => return TriBool::Unknown("point_missing".into()),
    };

    let target = (p.color.r, p.color.g, p.color.b);
    let tol = tolerance;

    let cur = ctx
        .sampler
        .sample_rgb_abs(&p.monitor, p.vx, p.vy, &p.sample.mode, p.sample.radius);

    match cur {
        None => TriBool::Unknown("sample_failed".into()),
        Some(cur_rgb) => {
            let diff = rgb_diff_max(cur_rgb, target);
            if diff <= tol {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}>{tol}"))
            }
        }
    }
}

fn eval_pixel_match_skill(skill_id: &str, tolerance: u8, ctx: &EvalContext) -> TriBool {
    let sid = skill_id.trim();
    if sid.is_empty() {
        return TriBool::Unknown("skill_id_empty".into());
    }

    let s = ctx.skills.iter().find(|s| s.id.as_str() == sid);
    let s = match s {
        Some(s) => s,
        None => return TriBool::Unknown("skill_missing".into()),
    };

    let pix = &s.pixel;
    let target = (pix.color.r, pix.color.g, pix.color.b);
    let tol = tolerance;

    let cur = ctx.sampler.sample_rgb_abs(
        &pix.monitor,
        pix.vx,
        pix.vy,
        &pix.sample.mode,
        pix.sample.radius,
    );

    match cur {
        None => TriBool::Unknown("sample_failed".into()),
        Some(cur_rgb) => {
            let diff = rgb_diff_max(cur_rgb, target);
            if diff <= tol {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}>{tol}"))
            }
        }
    }
}

fn eval_cast_bar_changed(point_id: &str, tolerance: u8, ctx: &EvalContext) -> TriBool {
    let pid = point_id.trim();
    if pid.is_empty() {
        return TriBool::Unknown("point_id_empty".into());
    }

    let baseline = match ctx.baseline {
        Some(b) => b,
        None => return TriBool::Unknown("baseline_provider_missing".into()),
    };

    let base_rgb = match baseline.get_point_baseline_rgb(pid) {
        Some(rgb) => rgb,
        None => return TriBool::Unknown("baseline_missing".into()),
    };

    let p = ctx.points.iter().find(|p| p.id.as_str() == pid);
    let p = match p {
        Some(p) => p,
        None => return TriBool::Unknown("point_missing".into()),
    };

    let tol = tolerance;

    let cur = ctx
        .sampler
        .sample_rgb_abs(&p.monitor, p.vx, p.vy, &p.sample.mode, p.sample.radius);

    match cur {
        None => TriBool::Unknown("sample_failed".into()),
        Some(cur_rgb) => {
            let diff = rgb_diff_max(cur_rgb, base_rgb);
            // "changed" = 当前与 baseline 的差异 > tolerance
            if diff > tol {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}<={tol}"))
            }
        }
    }
}

fn eval_skill_metric_ge(
    skill_id: &str,
    metric: &SkillMetric,
    count: u32,
    ctx: &EvalContext,
) -> TriBool {
    let sid = skill_id.trim();
    if sid.is_empty() {
        return TriBool::Unknown("skill_id_empty".into());
    }

    let provider = match ctx.metrics {
        Some(m) => m,
        None => return TriBool::Unknown("metrics_provider_missing".into()),
    };

    let cur = match provider.get_metric(sid, metric) {
        Some(v) => v,
        None => return TriBool::Unknown("metric_unavailable".into()),
    };

    let need = if count == 0 { 1 } else { count };
    if cur >= need {
        TriBool::True
    } else {
        TriBool::False(format!("cur={cur}<{need}"))
    }
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

/// RGB 最大通道差
fn rgb_diff_max(a: (u8, u8, u8), b: (u8, u8, u8)) -> u8 {
    let dr = (a.0 as i16 - b.0 as i16).unsigned_abs() as u8;
    let dg = (a.1 as i16 - b.1 as i16).unsigned_abs() as u8;
    let db = (a.2 as i16 - b.2 as i16).unsigned_abs() as u8;
    dr.max(dg).max(db)
}

// ===========================================================================
// 测试
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::nodes::{Expr, SkillMetric};
    use crate::models::point::Point;
    use crate::models::skill::{ColorRGB, PixelSpec, SampleConfig, Skill};
    use std::collections::HashMap;

    // ---- 测试替身 ----

    struct FixedSampler {
        rgb: (u8, u8, u8),
    }

    impl PixelSampler for FixedSampler {
        fn sample_rgb_abs(
            &self,
            _m: &str,
            _x: i32,
            _y: i32,
            _mode: &str,
            _r: u8,
        ) -> Option<(u8, u8, u8)> {
            Some(self.rgb)
        }
    }

    struct MapMetricProvider {
        data: HashMap<String, HashMap<SkillMetric, u32>>,
    }

    impl MetricProvider for MapMetricProvider {
        fn get_metric(&self, skill_id: &str, metric: &SkillMetric) -> Option<u32> {
            self.data.get(skill_id)?.get(metric).copied()
        }
    }

    struct MapBaselineProvider {
        data: HashMap<String, (u8, u8, u8)>,
    }

    impl BaselineProvider for MapBaselineProvider {
        fn get_point_baseline_rgb(&self, point_id: &str) -> Option<(u8, u8, u8)> {
            self.data.get(point_id).copied()
        }
    }

    // ---- fixtures ----

    fn make_point(id: &str, r: u8, g: u8, b: u8) -> Point {
        Point {
            id: id.into(),
            name: id.into(),
            monitor: "primary".into(),
            vx: 0,
            vy: 0,
            color: ColorRGB { r, g, b },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
            captured_at: String::new(),
            note: String::new(),
        }
    }

    fn make_skill(id: &str, r: u8, g: u8, b: u8) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            enabled: true,
            trigger_key: String::new(),
            cast: Default::default(),
            pixel: PixelSpec {
                monitor: "primary".into(),
                vx: 0,
                vy: 0,
                color: ColorRGB { r, g, b },
                tolerance: 0,
                sample: SampleConfig {
                    mode: "single".into(),
                    radius: 0,
                },
            },
            note: String::new(),
            game_id: 0,
            game_desc: String::new(),
            icon_url: String::new(),
            cooldown_ms: 0,
            radius: 0,
            shots_per_cycle: 1,
            ammo_stages: vec![],
        }
    }

    fn ctx_with_sampler(rgb: (u8, u8, u8)) -> (Vec<Point>, Vec<Skill>, FixedSampler) {
        let points = vec![make_point("pt1", 100, 150, 200)];
        let skills = vec![make_skill("sk1", 50, 60, 70)];
        let sampler = FixedSampler { rgb };
        (points, skills, sampler)
    }

    // ---- Kleene 逻辑真值表测试 ----

    #[test]
    fn test_const_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Const { value: true };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_const_false() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Const { value: false };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_not_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Not {
            child: Box::new(Expr::Const { value: true }),
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_not_false() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Not {
            child: Box::new(Expr::Const { value: false }),
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_and_all_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::And {
            children: vec![Expr::Const { value: true }, Expr::Const { value: true }],
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_and_one_false() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::And {
            children: vec![Expr::Const { value: true }, Expr::Const { value: false }],
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_or_one_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Or {
            children: vec![Expr::Const { value: false }, Expr::Const { value: true }],
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_or_all_false() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::Or {
            children: vec![Expr::Const { value: false }, Expr::Const { value: false }],
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    // ---- PixelMatchPoint 容差测试 ----

    #[test]
    fn test_pixel_point_match_exact() {
        let (points, skills, sampler) = ctx_with_sampler((100, 150, 200));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchPoint {
            point_id: "pt1".into(),
            tolerance: 0,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_pixel_point_match_within_tolerance() {
        let (points, skills, sampler) = ctx_with_sampler((120, 150, 200));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchPoint {
            point_id: "pt1".into(),
            tolerance: 30,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_pixel_point_mismatch() {
        let (points, skills, sampler) = ctx_with_sampler((130, 150, 200));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchPoint {
            point_id: "pt1".into(),
            tolerance: 20,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_pixel_point_missing() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchPoint {
            point_id: "nonexistent".into(),
            tolerance: 0,
        };
        assert!(evaluate(&expr, &ctx).is_unknown());
    }

    // ---- PixelMatchSkill 容差测试 ----

    #[test]
    fn test_pixel_skill_match() {
        let (points, skills, sampler) = ctx_with_sampler((50, 60, 70));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchSkill {
            skill_id: "sk1".into(),
            tolerance: 0,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_pixel_skill_mismatch() {
        let (points, skills, sampler) = ctx_with_sampler((80, 60, 70));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: None,
        };
        let expr = Expr::PixelMatchSkill {
            skill_id: "sk1".into(),
            tolerance: 20,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    // ---- SkillMetricGE ----

    #[test]
    fn test_skill_metric_ge_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        let mut inner = HashMap::new();
        inner.insert(SkillMetric::Success, 5);
        data.insert("sk1".into(), inner);
        let metrics = MapMetricProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: Some(&metrics),
            baseline: None,
        };
        let expr = Expr::SkillMetricGE {
            skill_id: "sk1".into(),
            metric: SkillMetric::Success,
            count: 3,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_skill_metric_ge_not_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        let mut inner = HashMap::new();
        inner.insert(SkillMetric::Success, 1);
        data.insert("sk1".into(), inner);
        let metrics = MapMetricProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: Some(&metrics),
            baseline: None,
        };
        let expr = Expr::SkillMetricGE {
            skill_id: "sk1".into(),
            metric: SkillMetric::Success,
            count: 3,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    // ---- CastBarChanged ----

    #[test]
    fn test_cast_bar_changed_true() {
        let (points, skills, sampler) = ctx_with_sampler((200, 150, 100)); // current
        let mut base_data = HashMap::new();
        base_data.insert("pt1".into(), (100, 150, 200)); // baseline
        let baseline = MapBaselineProvider { data: base_data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: Some(&baseline),
        };
        let expr = Expr::CastBarChanged {
            point_id: "pt1".into(),
            tolerance: 10,
        };
        // diff = max(100,0,100) = 100 > 10 → True
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_cast_bar_changed_false() {
        let (points, skills, sampler) = ctx_with_sampler((105, 150, 205)); // current
        let mut base_data = HashMap::new();
        base_data.insert("pt1".into(), (100, 150, 200)); // baseline
        let baseline = MapBaselineProvider { data: base_data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            baseline: Some(&baseline),
        };
        let expr = Expr::CastBarChanged {
            point_id: "pt1".into(),
            tolerance: 10,
        };
        // diff = max(5,0,5) = 5 <= 10 → False
        assert!(evaluate(&expr, &ctx).is_false());
    }

    // ---- 组合表达式 ----

    #[test]
    fn test_nested_and_or() {
        // (PixelMatchPoint(pt1, tol=30) AND SkillMetricGE(sk1, success >= 3))
        let (points, skills, sampler) = ctx_with_sampler((120, 150, 200));
        let mut data = HashMap::new();
        let mut inner = HashMap::new();
        inner.insert(SkillMetric::Success, 5);
        data.insert("sk1".into(), inner);
        let metrics = MapMetricProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: Some(&metrics),
            baseline: None,
        };
        let expr = Expr::And {
            children: vec![
                Expr::PixelMatchPoint {
                    point_id: "pt1".into(),
                    tolerance: 30,
                },
                Expr::SkillMetricGE {
                    skill_id: "sk1".into(),
                    metric: SkillMetric::Success,
                    count: 3,
                },
            ],
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }
}
