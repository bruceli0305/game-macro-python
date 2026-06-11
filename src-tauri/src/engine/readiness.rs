//! Skill readiness and expression evaluation helpers for `CycleExecutor`.

use crate::ast::evaluator::{EvalContext, TriBool, evaluate};
use crate::ast::nodes::Expr;
use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::runtime_config::SlotExprKey;
use crate::models::cycle::{ReadinessPolicy, SkillSlot};
use crate::models::skill::Skill;

impl<'a> CycleExecutor<'a> {
    pub(super) fn check_skill_ready_at(
        &self,
        slot: &SkillSlot,
        key: SlotExprKey,
        now_ms: u64,
    ) -> (bool, String) {
        let sid = slot.skill_id.trim();
        if sid.is_empty() {
            return (false, "skill_id_empty".into());
        }

        let Some(skill) = self.skills.iter().find(|s| s.id.as_str() == sid) else {
            return (false, "skill_missing".into());
        };
        if !skill.enabled {
            return (false, "skill_disabled".into());
        }
        if let Some(ready_at) = self.state.skill_ready_at_ms.get(sid) {
            if now_ms < *ready_at {
                return (false, format!("cooldown_until={ready_at}"));
            }
        }
        if !self.slot_can_fire_more_this_cycle(sid) {
            let shot_limit = skill.shots_per_cycle;
            return (false, format!("shots_per_cycle_exhausted={shot_limit}"));
        }
        if !self.skill_has_ammo(skill) {
            return (false, "ammo_unavailable".into());
        }

        let ctx = self.eval_context();
        let slot_exprs = self.slot_expr_cache.get(&key);

        if let Some(condition_expr) = slot_exprs.and_then(|exprs| exprs.condition_expr.as_ref()) {
            match evaluate(condition_expr, &ctx) {
                TriBool::True => {}
                TriBool::False(reason) => return (false, format!("condition_false: {reason}")),
                TriBool::Unknown(reason) => {
                    return (false, format!("condition_unknown: {reason}"));
                }
            }
        }

        let Some(readiness_expr) = slot_exprs.and_then(|exprs| exprs.readiness_expr.as_ref())
        else {
            return if slot_exprs
                .and_then(|exprs| exprs.condition_expr.as_ref())
                .is_some()
            {
                (true, "condition_true".into())
            } else {
                (true, "no_condition".into())
            };
        };

        match evaluate(readiness_expr, &ctx) {
            TriBool::True => (true, "condition_true readiness_true".into()),
            TriBool::False(reason) | TriBool::Unknown(reason)
                if slot.readiness_policy == ReadinessPolicy::Advisory =>
            {
                (true, format!("condition_true readiness_advisory: {reason}"))
            }
            TriBool::False(reason) => (false, format!("readiness_false: {reason}")),
            TriBool::Unknown(reason) => (false, format!("readiness_unknown: {reason}")),
        }
    }

    pub(super) fn evaluate_expr(&self, expr: &Expr) -> bool {
        evaluate(expr, &self.eval_context()).is_true()
    }

    /// Check whether a skill's pixel is "black" (all channels <= 5).
    /// Used by `CompletePolicy::CdBlack` in the attempt tracker.
    pub(super) fn skill_pixel_is_black(&self, skill_id: &str) -> bool {
        let Some(skill) = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)
        else {
            return false;
        };
        let pix = &skill.pixel;
        self.sampler
            .sample_rgb_abs(
                &pix.monitor,
                pix.vx,
                pix.vy,
                &pix.sample.mode,
                pix.sample.radius,
            )
            .is_some_and(|(r, g, b)| r.max(g).max(b) <= 5)
    }

    pub(super) fn skill_cooldown_ms(&self, skill_id: &str) -> Option<u32> {
        let skill = self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)?;
        let cooldown_ms = skill.cooldown_ms.max(skill.cast.cooldown_ms);
        (cooldown_ms > 0).then_some(cooldown_ms)
    }

    pub(super) fn slot_can_fire_more_this_cycle(&self, skill_id: &str) -> bool {
        let Some(shot_limit) = self.skill_shot_limit(skill_id) else {
            return true;
        };
        self.state
            .fired_count_in_cycle
            .get(skill_id)
            .copied()
            .unwrap_or(0)
            < shot_limit
    }

    pub(super) fn slot_shots_complete_this_cycle(&self, skill_id: &str) -> bool {
        let Some(shot_limit) = self.skill_shot_limit(skill_id) else {
            return self.state.fired_in_phase.contains(skill_id);
        };
        self.state
            .fired_count_in_cycle
            .get(skill_id)
            .copied()
            .unwrap_or(0)
            >= shot_limit
    }

    fn skill_shot_limit(&self, skill_id: &str) -> Option<u32> {
        match self
            .skills
            .iter()
            .find(|skill| skill.id.as_str() == skill_id)
            .map(|skill| skill.shots_per_cycle)
        {
            Some(0) => None,
            Some(limit) => Some(limit),
            None => Some(1),
        }
    }

    fn skill_has_ammo(&self, skill: &Skill) -> bool {
        if skill.ammo_stages.is_empty() {
            return true;
        }

        skill.ammo_stages.iter().any(|stage| {
            if stage.charges_left == 0 {
                return false;
            }
            let pix = &stage.pixel;
            self.sampler
                .sample_rgb_abs(
                    &pix.monitor,
                    pix.vx,
                    pix.vy,
                    &pix.sample.mode,
                    pix.sample.radius,
                )
                .is_some_and(|current| {
                    rgb_diff_max(current, (pix.color.r, pix.color.g, pix.color.b)) <= pix.tolerance
                })
        })
    }

    fn eval_context(&self) -> EvalContext<'_> {
        EvalContext {
            points: self.points,
            skills: self.skills,
            sampler: self.sampler,
            metrics: Some(&self.runtime),
            timers: Some(&self.runtime),
            markers: Some(&self.runtime),
            counters: Some(&self.runtime),
            baseline: None,
            cast_bar_roi: self.cast_bar_roi,
        }
    }
}

/// Maximum per-channel absolute difference between two RGB colors.
fn rgb_diff_max(a: (u8, u8, u8), b: (u8, u8, u8)) -> u8 {
    let dr = (a.0 as i16 - b.0 as i16).unsigned_abs() as u8;
    let dg = (a.1 as i16 - b.1 as i16).unsigned_abs() as u8;
    let db = (a.2 as i16 - b.2 as i16).unsigned_abs() as u8;
    dr.max(dg).max(db)
}
