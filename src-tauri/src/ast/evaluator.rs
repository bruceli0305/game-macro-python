use super::nodes::{Expr, SkillMetric};
use crate::models::point::Point;
use crate::models::skill::Skill;

// Runtime dependency traits used by the pure AST evaluator.
pub trait PixelSampler: Send + Sync {
    fn begin_tick(&self, _tick_ms: u64) {}

    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        sample_mode: &str,
        sample_radius: u8,
    ) -> Option<(u8, u8, u8)>;
}

pub trait MetricProvider: Send + Sync {
    fn get_metric(&self, skill_id: &str, metric: &SkillMetric) -> Option<u32>;
}

pub trait TimerProvider: Send + Sync {
    fn get_timer_elapsed_ms(&self, timer_id: &str) -> Option<u64>;
}

pub trait MarkerProvider: Send + Sync {
    fn get_marker(&self, marker_id: &str) -> Option<&str>;
}

pub trait CounterProvider: Send + Sync {
    fn get_counter(&self, counter_id: &str) -> Option<i64>;
}

pub trait BaselineProvider: Send + Sync {
    fn get_point_baseline_rgb(&self, point_id: &str) -> Option<(u8, u8, u8)>;
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CastBarRoiState {
    pub changed_from_baseline: bool,
    pub border_visible: bool,
    pub gone: bool,
    pub changed_ratio: f64,
    pub border_match_ratio: f64,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CastBarRoiStats {
    pub enabled: bool,
    pub sample_count: u64,
    pub cache_hit_count: u64,
    pub failed_sample_count: u64,
    pub last_latency_us: u64,
    pub avg_latency_us: u64,
    pub max_latency_us: u64,
    pub last_changed_ratio: f64,
    pub last_border_match_ratio: f64,
    pub last_changed_from_baseline: bool,
    pub last_border_visible: bool,
    pub last_gone: bool,
    pub last_error: String,
}

pub trait CastBarRoiProvider: Send + Sync {
    fn begin_tick(&self, _tick_ms: u64) {}
    fn get_cast_bar_roi_state(&self) -> Option<CastBarRoiState>;
    fn get_cast_bar_roi_stats(&self) -> Option<CastBarRoiStats> {
        None
    }
}

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

pub struct EvalContext<'a> {
    pub points: &'a [Point],
    pub skills: &'a [Skill],
    pub sampler: &'a dyn PixelSampler,
    pub metrics: Option<&'a dyn MetricProvider>,
    pub timers: Option<&'a dyn TimerProvider>,
    pub markers: Option<&'a dyn MarkerProvider>,
    pub counters: Option<&'a dyn CounterProvider>,
    pub baseline: Option<&'a dyn BaselineProvider>,
    pub cast_bar_roi: Option<&'a dyn CastBarRoiProvider>,
}

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
        } => eval_pixel_point(point_id, *tolerance, PixelPredicate::Match, ctx),
        Expr::PixelPointNotMatch {
            point_id,
            tolerance,
        } => eval_pixel_point(point_id, *tolerance, PixelPredicate::NotMatch, ctx),
        Expr::PixelPointBlack {
            point_id,
            tolerance,
        } => eval_pixel_point(point_id, *tolerance, PixelPredicate::Black, ctx),
        Expr::PixelPointNotBlack {
            point_id,
            tolerance,
        } => eval_pixel_point(point_id, *tolerance, PixelPredicate::NotBlack, ctx),
        Expr::PixelMatchSkill {
            skill_id,
            tolerance,
        } => eval_pixel_skill(skill_id, *tolerance, PixelPredicate::Match, ctx),
        Expr::PixelSkillNotMatch {
            skill_id,
            tolerance,
        } => eval_pixel_skill(skill_id, *tolerance, PixelPredicate::NotMatch, ctx),
        Expr::PixelSkillBlack {
            skill_id,
            tolerance,
        } => eval_pixel_skill(skill_id, *tolerance, PixelPredicate::Black, ctx),
        Expr::PixelSkillNotBlack {
            skill_id,
            tolerance,
        } => eval_pixel_skill(skill_id, *tolerance, PixelPredicate::NotBlack, ctx),
        Expr::CastBarChanged {
            point_id,
            tolerance,
        } => eval_cast_bar_changed(point_id, *tolerance, ctx),
        Expr::CastBarRoiChanged => eval_cast_bar_roi(ctx, CastBarRoiPredicate::Changed),
        Expr::CastBarRoiBorderVisible => eval_cast_bar_roi(ctx, CastBarRoiPredicate::BorderVisible),
        Expr::CastBarRoiGone => eval_cast_bar_roi(ctx, CastBarRoiPredicate::Gone),
        Expr::SkillMetricGE {
            skill_id,
            metric,
            count,
        } => eval_skill_metric_ge(skill_id, metric, *count, ctx),
        Expr::MarkerEq { marker_id, value } => eval_marker(marker_id, value, true, ctx),
        Expr::MarkerNe { marker_id, value } => eval_marker(marker_id, value, false, ctx),
        Expr::TimerElapsedGE { timer_id, ms } => eval_timer_elapsed_ge(timer_id, *ms, ctx),
        Expr::TimerElapsedLT { timer_id, ms } => eval_timer_elapsed_lt(timer_id, *ms, ctx),
        Expr::CounterGE { counter_id, value } => eval_counter(counter_id, *value, ">=", ctx),
        Expr::CounterEq { counter_id, value } => eval_counter(counter_id, *value, "==", ctx),
        Expr::CounterGT { counter_id, value } => eval_counter(counter_id, *value, ">", ctx),
    }
}

// ---------------------------------------------------------------------------
// Kleene logic.
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
// Atomic evaluation.
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
enum PixelPredicate {
    Match,
    NotMatch,
    Black,
    NotBlack,
}

fn eval_pixel_point(
    point_id: &str,
    tolerance: u8,
    predicate: PixelPredicate,
    ctx: &EvalContext,
) -> TriBool {
    let pid = point_id.trim();
    if pid.is_empty() {
        return TriBool::Unknown("point_id_empty".into());
    }

    let p = ctx.points.iter().find(|p| p.id.as_str() == pid);
    let p = match p {
        Some(p) => p,
        None => return TriBool::Unknown("point_missing".into()),
    };

    let cur = ctx
        .sampler
        .sample_rgb_abs(&p.monitor, p.vx, p.vy, &p.sample.mode, p.sample.radius);

    match cur {
        None => TriBool::Unknown("sample_failed".into()),
        Some(cur_rgb) => eval_pixel_predicate(
            cur_rgb,
            (p.color.r, p.color.g, p.color.b),
            tolerance,
            predicate,
        ),
    }
}

fn eval_pixel_skill(
    skill_id: &str,
    tolerance: u8,
    predicate: PixelPredicate,
    ctx: &EvalContext,
) -> TriBool {
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
    let cur = ctx.sampler.sample_rgb_abs(
        &pix.monitor,
        pix.vx,
        pix.vy,
        &pix.sample.mode,
        pix.sample.radius,
    );

    match cur {
        None => TriBool::Unknown("sample_failed".into()),
        Some(cur_rgb) => eval_pixel_predicate(
            cur_rgb,
            (pix.color.r, pix.color.g, pix.color.b),
            tolerance,
            predicate,
        ),
    }
}

fn eval_pixel_predicate(
    cur_rgb: (u8, u8, u8),
    target: (u8, u8, u8),
    tolerance: u8,
    predicate: PixelPredicate,
) -> TriBool {
    match predicate {
        PixelPredicate::Match => {
            let diff = rgb_diff_max(cur_rgb, target);
            if diff <= tolerance {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}>{tolerance}"))
            }
        }
        PixelPredicate::NotMatch => {
            let diff = rgb_diff_max(cur_rgb, target);
            if diff > tolerance {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}<={tolerance}"))
            }
        }
        PixelPredicate::Black => {
            let max_channel = cur_rgb.0.max(cur_rgb.1).max(cur_rgb.2);
            if max_channel <= tolerance {
                TriBool::True
            } else {
                TriBool::False(format!("max_channel={max_channel}>{tolerance}"))
            }
        }
        PixelPredicate::NotBlack => {
            let max_channel = cur_rgb.0.max(cur_rgb.1).max(cur_rgb.2);
            if max_channel > tolerance {
                TriBool::True
            } else {
                TriBool::False(format!("max_channel={max_channel}<={tolerance}"))
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
            // "changed" means current color differs from baseline beyond tolerance.
            if diff > tol {
                TriBool::True
            } else {
                TriBool::False(format!("diff={diff}<={tol}"))
            }
        }
    }
}

#[derive(Clone, Copy)]
enum CastBarRoiPredicate {
    Changed,
    BorderVisible,
    Gone,
}

fn eval_cast_bar_roi(ctx: &EvalContext, predicate: CastBarRoiPredicate) -> TriBool {
    let provider = match ctx.cast_bar_roi {
        Some(provider) => provider,
        None => return TriBool::Unknown("cast_bar_roi_provider_missing".into()),
    };
    let state = match provider.get_cast_bar_roi_state() {
        Some(state) => state,
        None => return TriBool::Unknown("cast_bar_roi_unavailable".into()),
    };
    match predicate {
        CastBarRoiPredicate::Changed => {
            if state.changed_from_baseline {
                TriBool::True
            } else {
                TriBool::False(format!("changed_ratio={:.4}", state.changed_ratio))
            }
        }
        CastBarRoiPredicate::BorderVisible => {
            if state.border_visible {
                TriBool::True
            } else {
                TriBool::False(format!(
                    "border_match_ratio={:.4}",
                    state.border_match_ratio
                ))
            }
        }
        CastBarRoiPredicate::Gone => {
            if state.gone {
                TriBool::True
            } else {
                TriBool::False("cast_bar_roi_visible".into())
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

fn eval_marker(marker_id: &str, value: &str, expect_equal: bool, ctx: &EvalContext) -> TriBool {
    let mid = marker_id.trim();
    if mid.is_empty() {
        return TriBool::Unknown("marker_id_empty".into());
    }
    let provider = match ctx.markers {
        Some(provider) => provider,
        None => return TriBool::Unknown("marker_provider_missing".into()),
    };
    let current = match provider.get_marker(mid) {
        Some(current) => current,
        None => return TriBool::Unknown("marker_unavailable".into()),
    };
    let matched = current == value;
    if matched == expect_equal {
        TriBool::True
    } else if expect_equal {
        TriBool::False(format!("marker={current}!={value}"))
    } else {
        TriBool::False(format!("marker={current}=={value}"))
    }
}

fn eval_timer_elapsed_ge(timer_id: &str, ms: u64, ctx: &EvalContext) -> TriBool {
    let tid = timer_id.trim();
    if tid.is_empty() {
        return TriBool::Unknown("timer_id_empty".into());
    }
    let provider = match ctx.timers {
        Some(provider) => provider,
        None => return TriBool::Unknown("timer_provider_missing".into()),
    };
    let elapsed = match provider.get_timer_elapsed_ms(tid) {
        Some(elapsed) => elapsed,
        None => return TriBool::Unknown("timer_unavailable".into()),
    };
    if elapsed >= ms {
        TriBool::True
    } else {
        TriBool::False(format!("elapsed={elapsed}<{ms}"))
    }
}

fn eval_timer_elapsed_lt(timer_id: &str, ms: u64, ctx: &EvalContext) -> TriBool {
    let tid = timer_id.trim();
    if tid.is_empty() {
        return TriBool::Unknown("timer_id_empty".into());
    }
    let provider = match ctx.timers {
        Some(provider) => provider,
        None => return TriBool::Unknown("timer_provider_missing".into()),
    };
    let elapsed = match provider.get_timer_elapsed_ms(tid) {
        Some(elapsed) => elapsed,
        None => return TriBool::Unknown("timer_unavailable".into()),
    };
    if elapsed < ms {
        TriBool::True
    } else {
        TriBool::False(format!("elapsed={elapsed}>={ms}"))
    }
}

fn eval_counter(counter_id: &str, value: i64, op: &str, ctx: &EvalContext) -> TriBool {
    let cid = counter_id.trim();
    if cid.is_empty() {
        return TriBool::Unknown("counter_id_empty".into());
    }
    let provider = match ctx.counters {
        Some(provider) => provider,
        None => return TriBool::Unknown("counter_provider_missing".into()),
    };
    let current = match provider.get_counter(cid) {
        Some(current) => current,
        None => return TriBool::Unknown("counter_unavailable".into()),
    };
    let matched = match op {
        ">=" => current >= value,
        "==" => current == value,
        ">" => current > value,
        _ => false,
    };
    if matched {
        TriBool::True
    } else {
        TriBool::False(format!("counter={current}{op}{value} false"))
    }
}

fn rgb_diff_max(a: (u8, u8, u8), b: (u8, u8, u8)) -> u8 {
    let dr = (a.0 as i16 - b.0 as i16).unsigned_abs() as u8;
    let dg = (a.1 as i16 - b.1 as i16).unsigned_abs() as u8;
    let db = (a.2 as i16 - b.2 as i16).unsigned_abs() as u8;
    dr.max(dg).max(db)
}

// ===========================================================================
// Tests.
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::nodes::{Expr, SkillMetric};
    use crate::models::point::Point;
    use crate::models::skill::{ColorRGB, PixelSpec, SampleConfig, Skill};
    use std::collections::HashMap;

    // ---- Test doubles ----

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

    struct MapTimerProvider {
        data: HashMap<String, u64>,
    }

    impl TimerProvider for MapTimerProvider {
        fn get_timer_elapsed_ms(&self, timer_id: &str) -> Option<u64> {
            self.data.get(timer_id).copied()
        }
    }

    struct MapMarkerProvider {
        data: HashMap<String, String>,
    }

    impl MarkerProvider for MapMarkerProvider {
        fn get_marker(&self, marker_id: &str) -> Option<&str> {
            self.data.get(marker_id).map(String::as_str)
        }
    }

    struct MapCounterProvider {
        data: HashMap<String, i64>,
    }

    impl CounterProvider for MapCounterProvider {
        fn get_counter(&self, counter_id: &str) -> Option<i64> {
            self.data.get(counter_id).copied()
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

    struct FixedCastBarRoiProvider {
        state: Option<CastBarRoiState>,
    }

    impl CastBarRoiProvider for FixedCastBarRoiProvider {
        fn get_cast_bar_roi_state(&self) -> Option<CastBarRoiState> {
            self.state
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

    // ---- Kleene truth table tests ----

    #[test]
    fn test_const_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::Or {
            children: vec![Expr::Const { value: false }, Expr::Const { value: false }],
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    // ---- PixelMatchPoint tolerance tests ----

    #[test]
    fn test_pixel_point_match_exact() {
        let (points, skills, sampler) = ctx_with_sampler((100, 150, 200));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::PixelMatchPoint {
            point_id: "nonexistent".into(),
            tolerance: 0,
        };
        assert!(evaluate(&expr, &ctx).is_unknown());
    }

    // ---- PixelMatchSkill tolerance tests ----

    #[test]
    fn test_pixel_skill_match() {
        let (points, skills, sampler) = ctx_with_sampler((50, 60, 70));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::PixelMatchSkill {
            skill_id: "sk1".into(),
            tolerance: 20,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_pixel_point_not_match_true() {
        let (points, skills, sampler) = ctx_with_sampler((130, 150, 200));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::PixelPointNotMatch {
            point_id: "pt1".into(),
            tolerance: 20,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_pixel_skill_black_true() {
        let (points, skills, sampler) = ctx_with_sampler((2, 3, 4));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::PixelSkillBlack {
            skill_id: "sk1".into(),
            tolerance: 5,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_pixel_point_not_black_false() {
        let (points, skills, sampler) = ctx_with_sampler((2, 3, 4));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::PixelPointNotBlack {
            point_id: "pt1".into(),
            tolerance: 5,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::SkillMetricGE {
            skill_id: "sk1".into(),
            metric: SkillMetric::Success,
            count: 3,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_timer_elapsed_ge_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("burst".into(), 8_000);
        let timers = MapTimerProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: Some(&timers),
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::TimerElapsedGE {
            timer_id: "burst".into(),
            ms: 5_000,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_timer_elapsed_lt_not_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("burst".into(), 8_000);
        let timers = MapTimerProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: Some(&timers),
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::TimerElapsedLT {
            timer_id: "burst".into(),
            ms: 5_000,
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_marker_eq_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("weapon".into(), "main".into());
        let markers = MapMarkerProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: Some(&markers),
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::MarkerEq {
            marker_id: "weapon".into(),
            value: "main".into(),
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_marker_ne_not_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("weapon".into(), "main".into());
        let markers = MapMarkerProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: Some(&markers),
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::MarkerNe {
            marker_id: "weapon".into(),
            value: "main".into(),
        };
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_counter_ge_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("main_wp2_count".into(), 2);
        let counters = MapCounterProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: Some(&counters),
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::CounterGE {
            counter_id: "main_wp2_count".into(),
            value: 2,
        };
        assert!(evaluate(&expr, &ctx).is_true());
    }

    #[test]
    fn test_counter_gt_not_satisfied() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let mut data = HashMap::new();
        data.insert("main_wp2_count".into(), 2);
        let counters = MapCounterProvider { data };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: Some(&counters),
            baseline: None,
            cast_bar_roi: None,
        };
        let expr = Expr::CounterGT {
            counter_id: "main_wp2_count".into(),
            value: 2,
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

            timers: None,
            markers: None,
            counters: None,
            baseline: Some(&baseline),
            cast_bar_roi: None,
        };
        let expr = Expr::CastBarChanged {
            point_id: "pt1".into(),
            tolerance: 10,
        };
        // diff = max(100,0,100) = 100 > 10 -> True
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

            timers: None,
            markers: None,
            counters: None,
            baseline: Some(&baseline),
            cast_bar_roi: None,
        };
        let expr = Expr::CastBarChanged {
            point_id: "pt1".into(),
            tolerance: 10,
        };
        // diff = max(5,0,5) = 5 <= 10 -> False
        assert!(evaluate(&expr, &ctx).is_false());
    }

    #[test]
    fn test_cast_bar_roi_changed_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let roi = FixedCastBarRoiProvider {
            state: Some(CastBarRoiState {
                changed_from_baseline: true,
                border_visible: false,
                gone: false,
                changed_ratio: 0.5,
                border_match_ratio: 0.0,
            }),
        };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: Some(&roi),
        };

        assert!(evaluate(&Expr::CastBarRoiChanged, &ctx).is_true());
    }

    #[test]
    fn test_cast_bar_roi_border_visible_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let roi = FixedCastBarRoiProvider {
            state: Some(CastBarRoiState {
                changed_from_baseline: false,
                border_visible: true,
                gone: false,
                changed_ratio: 0.0,
                border_match_ratio: 0.6,
            }),
        };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: Some(&roi),
        };

        assert!(evaluate(&Expr::CastBarRoiBorderVisible, &ctx).is_true());
    }

    #[test]
    fn test_cast_bar_roi_gone_true() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let roi = FixedCastBarRoiProvider {
            state: Some(CastBarRoiState {
                changed_from_baseline: false,
                border_visible: false,
                gone: true,
                changed_ratio: 0.0,
                border_match_ratio: 0.0,
            }),
        };
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: Some(&roi),
        };

        assert!(evaluate(&Expr::CastBarRoiGone, &ctx).is_true());
    }

    #[test]
    fn test_cast_bar_roi_provider_missing_is_unknown() {
        let (points, skills, sampler) = ctx_with_sampler((0, 0, 0));
        let ctx = EvalContext {
            points: &points,
            skills: &skills,
            sampler: &sampler,
            metrics: None,
            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
        };

        assert!(evaluate(&Expr::CastBarRoiChanged, &ctx).is_unknown());
    }

    // ---- 缁勫悎琛ㄨ揪寮?----

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

            timers: None,
            markers: None,
            counters: None,
            baseline: None,
            cast_bar_roi: None,
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
