//! JSON → Expr 编译 + 语义校验 + 探针收集

use super::nodes::{Expr, SkillMetric};
use serde_json::Value;

/// 编译诊断
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Diagnostic {
    pub level: DiagnosticLevel,
    pub code: String,
    pub path: String,
    pub message: String,
    pub detail: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagnosticLevel {
    Error,
    Warning,
}

impl Diagnostic {
    pub fn error(code: &str, path: &str, message: &str) -> Self {
        Self {
            level: DiagnosticLevel::Error,
            code: code.into(),
            path: path.into(),
            message: message.into(),
            detail: String::new(),
        }
    }

    pub fn error_detail(code: &str, path: &str, message: &str, detail: &str) -> Self {
        Self {
            level: DiagnosticLevel::Error,
            code: code.into(),
            path: path.into(),
            message: message.into(),
            detail: detail.into(),
        }
    }

    pub fn warning(code: &str, path: &str, message: &str) -> Self {
        Self {
            level: DiagnosticLevel::Warning,
            code: code.into(),
            path: path.into(),
            message: message.into(),
            detail: String::new(),
        }
    }

    pub fn is_error(&self) -> bool {
        matches!(self.level, DiagnosticLevel::Error)
    }
}

/// 探针需求（编译后收集的所有引用）
#[derive(Debug, Clone, Default)]
pub struct ProbeRequirements {
    pub point_ids: Vec<String>,
    pub skill_pixel_ids: Vec<String>,
    pub skill_metric_ids: Vec<String>,
}

impl ProbeRequirements {
    pub fn merge(&mut self, other: &ProbeRequirements) {
        for id in &other.point_ids {
            if !self.point_ids.contains(id) {
                self.point_ids.push(id.clone());
            }
        }
        for id in &other.skill_pixel_ids {
            if !self.skill_pixel_ids.contains(id) {
                self.skill_pixel_ids.push(id.clone());
            }
        }
        for id in &other.skill_metric_ids {
            if !self.skill_metric_ids.contains(id) {
                self.skill_metric_ids.push(id.clone());
            }
        }
    }
}

/// 编译结果
#[derive(Debug)]
pub struct CompileResult {
    pub expr: Option<Expr>,
    pub diagnostics: Vec<Diagnostic>,
    pub probes: ProbeRequirements,
}

impl CompileResult {
    pub fn has_errors(&self) -> bool {
        self.diagnostics.iter().any(|d| d.is_error())
    }
}

/// 已知点位的 ID 集合（用于引用校验，可选）
pub struct CompileContext {
    pub point_ids: Vec<String>,
    pub skill_ids: Vec<String>,
    /// skill_id → 是否已配置 pixel（用于 PixelMatchSkill 时产生 warning）
    pub skill_has_pixel: Vec<(String, bool)>,
}

const ALLOWED_METRICS: &[&str] = &[
    "success",
    "attempt_started",
    "key_sent_ok",
    "cast_started",
    "fail",
];

// ---------------------------------------------------------------------------
// 主入口
// ---------------------------------------------------------------------------

/// 编译 JSON AST 为 Expr
pub fn compile_expr_json(json: &Value, path: &str) -> CompileResult {
    let mut diags = Vec::new();
    let mut probes = ProbeRequirements::default();

    let expr = decode_expr(json, path, &mut diags);

    if let Some(ref e) = expr {
        semantic_validate(e, path, &mut diags);
        collect_probes(e, &mut probes);
    }

    CompileResult {
        expr,
        diagnostics: diags,
        probes,
    }
}

// ---------------------------------------------------------------------------
// JSON decode
// ---------------------------------------------------------------------------

fn decode_expr(json: &Value, path: &str, diags: &mut Vec<Diagnostic>) -> Option<Expr> {
    let obj = match json.as_object() {
        Some(o) => o,
        None => {
            diags.push(Diagnostic::error(
                "expr.not_object",
                path,
                "表达式必须是 JSON 对象",
            ));
            return None;
        }
    };

    let typ = obj.get("type").and_then(|v| v.as_str()).unwrap_or("");
    if typ.is_empty() {
        diags.push(Diagnostic::error(
            "expr.type.missing",
            path,
            "缺少 type 字段",
        ));
        return None;
    }

    match typ {
        "and" => {
            let children = decode_children(json, path, diags);
            if children.is_empty() {
                diags.push(Diagnostic::error(
                    "expr.children.empty",
                    path,
                    "AND 的 children 不能为空",
                ));
                return None;
            }
            Some(Expr::And { children })
        }
        "or" => {
            let children = decode_children(json, path, diags);
            if children.is_empty() {
                diags.push(Diagnostic::error(
                    "expr.children.empty",
                    path,
                    "OR 的 children 不能为空",
                ));
                return None;
            }
            Some(Expr::Or { children })
        }
        "not" => {
            let child_json = obj.get("child");
            match child_json {
                None => {
                    diags.push(Diagnostic::error(
                        "expr.not.no_child",
                        path,
                        "NOT 必须包含 child",
                    ));
                    None
                }
                Some(c) => {
                    let child = decode_expr(c, &format!("{path}.child"), diags)?;
                    Some(Expr::Not {
                        child: Box::new(child),
                    })
                }
            }
        }
        "const" => {
            let value = obj.get("value").and_then(|v| v.as_bool()).unwrap_or(false);
            Some(Expr::Const { value })
        }
        "pixel_point" => {
            let point_id = obj
                .get("point_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let tolerance = obj.get("tolerance").and_then(|v| v.as_u64()).unwrap_or(0) as u8;
            Some(Expr::PixelMatchPoint {
                point_id,
                tolerance,
            })
        }
        "pixel_skill" => {
            let skill_id = obj
                .get("skill_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let tolerance = obj.get("tolerance").and_then(|v| v.as_u64()).unwrap_or(0) as u8;
            Some(Expr::PixelMatchSkill {
                skill_id,
                tolerance,
            })
        }
        "cast_bar_changed" => {
            let point_id = obj
                .get("point_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let tolerance = obj.get("tolerance").and_then(|v| v.as_u64()).unwrap_or(0) as u8;
            Some(Expr::CastBarChanged {
                point_id,
                tolerance,
            })
        }
        "skill_metric_ge" => {
            let skill_id = obj
                .get("skill_id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let metric_str = obj.get("metric").and_then(|v| v.as_str()).unwrap_or("");
            let metric = match metric_str {
                "success" => SkillMetric::Success,
                "attempt_started" => SkillMetric::AttemptStarted,
                "key_sent_ok" => SkillMetric::KeySentOk,
                "cast_started" => SkillMetric::CastStarted,
                "fail" => SkillMetric::Fail,
                other => {
                    diags.push(Diagnostic::error(
                        "expr.metric.invalid",
                        path,
                        &format!("非法 metric: {other}"),
                    ));
                    return None;
                }
            };
            let count = obj.get("count").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
            Some(Expr::SkillMetricGE {
                skill_id,
                metric,
                count,
            })
        }
        other => {
            diags.push(Diagnostic::error(
                "expr.type.unknown",
                path,
                &format!("未知 type: {other}"),
            ));
            None
        }
    }
}

fn decode_children(json: &Value, path: &str, diags: &mut Vec<Diagnostic>) -> Vec<Expr> {
    let arr = match json.get("children").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => return vec![],
    };
    arr.iter()
        .enumerate()
        .filter_map(|(i, v)| decode_expr(v, &format!("{path}.children[{i}]"), diags))
        .collect()
}

// ---------------------------------------------------------------------------
// 语义校验
// ---------------------------------------------------------------------------

fn semantic_validate(expr: &Expr, path: &str, diags: &mut Vec<Diagnostic>) {
    match expr {
        Expr::And { children } | Expr::Or { children } => {
            for (i, c) in children.iter().enumerate() {
                semantic_validate(c, &format!("{path}.children[{i}]"), diags);
            }
        }
        Expr::Not { child } => semantic_validate(child, &format!("{path}.child"), diags),
        Expr::Const { .. } => {}
        Expr::PixelMatchPoint { point_id, .. } | Expr::CastBarChanged { point_id, .. } => {
            if point_id.trim().is_empty() {
                diags.push(Diagnostic::error(
                    "expr.point_id.empty",
                    path,
                    "point_id 不能为空",
                ));
            }
        }
        Expr::PixelMatchSkill { skill_id, .. } => {
            if skill_id.trim().is_empty() {
                diags.push(Diagnostic::error(
                    "expr.skill_id.empty",
                    path,
                    "skill_id 不能为空",
                ));
            }
        }
        Expr::SkillMetricGE {
            skill_id,
            metric,
            count,
        } => {
            if skill_id.trim().is_empty() {
                diags.push(Diagnostic::error(
                    "expr.skill_id.empty",
                    path,
                    "skill_id 不能为空",
                ));
            }
            let metric_str = match metric {
                SkillMetric::Success => "success",
                SkillMetric::AttemptStarted => "attempt_started",
                SkillMetric::KeySentOk => "key_sent_ok",
                SkillMetric::CastStarted => "cast_started",
                SkillMetric::Fail => "fail",
            };
            if !ALLOWED_METRICS.contains(&metric_str) {
                diags.push(Diagnostic::error(
                    "expr.metric.invalid",
                    path,
                    &format!("非法 metric: {metric_str}"),
                ));
            }
            if *count == 0 {
                diags.push(Diagnostic::error(
                    "expr.count.zero",
                    path,
                    "count 必须 >= 1",
                ));
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 探针收集
// ---------------------------------------------------------------------------

fn collect_probes(expr: &Expr, probes: &mut ProbeRequirements) {
    match expr {
        Expr::And { children } | Expr::Or { children } => {
            for c in children {
                collect_probes(c, probes);
            }
        }
        Expr::Not { child } => collect_probes(child, probes),
        Expr::Const { .. } => {}
        Expr::PixelMatchPoint { point_id, .. } | Expr::CastBarChanged { point_id, .. } => {
            let pid = point_id.trim();
            if !pid.is_empty() && !probes.point_ids.contains(&pid.to_string()) {
                probes.point_ids.push(pid.to_string());
            }
        }
        Expr::PixelMatchSkill { skill_id, .. } => {
            let sid = skill_id.trim();
            if !sid.is_empty() && !probes.skill_pixel_ids.contains(&sid.to_string()) {
                probes.skill_pixel_ids.push(sid.to_string());
            }
        }
        Expr::SkillMetricGE { skill_id, .. } => {
            let sid = skill_id.trim();
            if !sid.is_empty() && !probes.skill_metric_ids.contains(&sid.to_string()) {
                probes.skill_metric_ids.push(sid.to_string());
            }
        }
    }
}

// ===========================================================================
// 测试
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn compile(json: Value) -> CompileResult {
        compile_expr_json(&json, "$")
    }

    #[test]
    fn test_decode_const_true() {
        let r = compile(json!({"type": "const", "value": true}));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::Const { value: true })));
    }

    #[test]
    fn test_decode_const_false() {
        let r = compile(json!({"type": "const", "value": false}));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::Const { value: false })));
    }

    #[test]
    fn test_decode_and() {
        let r = compile(json!({
            "type": "and",
            "children": [
                {"type": "const", "value": true},
                {"type": "const", "value": false}
            ]
        }));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::And { .. })));
    }

    #[test]
    fn test_decode_not() {
        let r = compile(json!({
            "type": "not",
            "child": {"type": "const", "value": true}
        }));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::Not { .. })));
    }

    #[test]
    fn test_decode_pixel_point() {
        let r = compile(json!({
            "type": "pixel_point",
            "point_id": "pt1",
            "tolerance": 20
        }));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::PixelMatchPoint { .. })));
        assert_eq!(r.probes.point_ids, vec!["pt1"]);
    }

    #[test]
    fn test_decode_pixel_skill() {
        let r = compile(json!({
            "type": "pixel_skill",
            "skill_id": "sk1",
            "tolerance": 15
        }));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::PixelMatchSkill { .. })));
        assert_eq!(r.probes.skill_pixel_ids, vec!["sk1"]);
    }

    #[test]
    fn test_decode_skill_metric_ge() {
        let r = compile(json!({
            "type": "skill_metric_ge",
            "skill_id": "sk1",
            "metric": "success",
            "count": 3
        }));
        assert!(!r.has_errors());
        assert!(matches!(r.expr, Some(Expr::SkillMetricGE { .. })));
        assert_eq!(r.probes.skill_metric_ids, vec!["sk1"]);
    }

    #[test]
    fn test_error_empty_children() {
        let r = compile(json!({"type": "and", "children": []}));
        assert!(r.has_errors());
    }

    #[test]
    fn test_error_missing_type() {
        let r = compile(json!({"value": true}));
        assert!(r.has_errors());
    }

    #[test]
    fn test_error_invalid_metric() {
        let r = compile(json!({
            "type": "skill_metric_ge",
            "skill_id": "sk1",
            "metric": "invalid",
            "count": 1
        }));
        assert!(r.has_errors());
    }

    #[test]
    fn test_error_zero_count() {
        let r = compile(json!({
            "type": "skill_metric_ge",
            "skill_id": "sk1",
            "metric": "success",
            "count": 0
        }));
        assert!(r.has_errors());
    }

    #[test]
    fn test_probes_collect_nested() {
        let r = compile(json!({
            "type": "and",
            "children": [
                {"type": "pixel_point", "point_id": "pt1", "tolerance": 10},
                {"type": "pixel_skill", "skill_id": "sk1", "tolerance": 5},
                {"type": "skill_metric_ge", "skill_id": "sk1", "metric": "success", "count": 3}
            ]
        }));
        assert!(!r.has_errors());
        assert_eq!(r.probes.point_ids, vec!["pt1"]);
        assert_eq!(r.probes.skill_pixel_ids, vec!["sk1"]);
        assert_eq!(r.probes.skill_metric_ids, vec!["sk1"]);
    }
}
