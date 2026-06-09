//! 运行时聚合指标 + MetricProvider + 基础状态
//!
//! 对齐 python-legacy/rotation_editor/core/runtime/state/store.py

use crate::ast::nodes::SkillMetric;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// SkillRuntimeState
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default)]
pub struct SkillRuntimeState {
    pub skill_id: String,

    // 聚合指标
    pub node_exec: u32,
    pub ready_false: u32,
    pub skipped_disabled: u32,
    pub skipped_lock_busy: u32,
    pub attempt_started: u32,
    pub key_sent_ok: u32,
    pub cast_started: u32,
    pub success: u32,
    pub fail: u32,
    pub fail_by_reason: HashMap<String, u32>,

    // 当前 attempt
    pub current_attempt_id: String,
    pub current_stage: AttemptStage,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum AttemptStage {
    #[default]
    Idle,
    Preparing,
    StartWait,
    Casting,
    CompleteWait,
    Success,
    Failed,
    Stopped,
}

// ---------------------------------------------------------------------------
// EngineState
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default)]
pub struct EngineState {
    pub running: bool,
    pub paused: bool,
    pub preset_id: String,
    pub stop_reason: String,
}

// ---------------------------------------------------------------------------
// RuntimeState
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default)]
pub struct RuntimeState {
    pub engine: EngineState,
    pub skills: HashMap<String, SkillRuntimeState>,
    pub markers: HashMap<String, String>,
    pub timers: HashMap<String, u64>,
    pub counters: HashMap<String, i64>,
    pub now_ms: u64,
}

impl RuntimeState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_now_ms(&mut self, now_ms: u64) {
        self.now_ms = now_ms;
    }

    fn ensure_skill(&mut self, skill_id: &str) -> &mut SkillRuntimeState {
        let sid = skill_id.trim().to_string();
        self.skills
            .entry(sid.clone())
            .or_insert_with(|| SkillRuntimeState {
                skill_id: sid,
                ..Default::default()
            })
    }

    // ---- engine ----

    pub fn engine_started(&mut self, preset_id: &str) {
        self.engine.running = true;
        self.engine.paused = false;
        self.engine.preset_id = preset_id.into();
        self.engine.stop_reason.clear();
    }

    pub fn engine_stopped(&mut self, reason: &str) {
        self.engine.running = false;
        self.engine.paused = false;
        self.engine.stop_reason = reason.into();
    }

    pub fn engine_paused(&mut self) {
        self.engine.paused = true;
    }
    pub fn engine_resumed(&mut self) {
        self.engine.paused = false;
    }

    // ---- skill aggregates ----

    pub fn mark_node_exec(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).node_exec += 1;
    }

    pub fn mark_ready_false(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).ready_false += 1;
    }

    pub fn mark_skipped_disabled(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).skipped_disabled += 1;
    }

    pub fn mark_skipped_lock_busy(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).skipped_lock_busy += 1;
    }

    pub fn mark_attempt_started(&mut self, skill_id: &str) {
        let st = self.ensure_skill(skill_id);
        st.attempt_started += 1;
        st.current_stage = AttemptStage::Preparing;
    }

    pub fn mark_key_sent_ok(&mut self, skill_id: &str) {
        let st = self.ensure_skill(skill_id);
        st.key_sent_ok += 1;
        st.current_stage = AttemptStage::StartWait;
    }

    pub fn mark_cast_started(&mut self, skill_id: &str) {
        let st = self.ensure_skill(skill_id);
        st.cast_started += 1;
        st.current_stage = AttemptStage::Casting;
    }

    pub fn mark_complete_wait_started(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).current_stage = AttemptStage::CompleteWait;
    }

    pub fn mark_success(&mut self, skill_id: &str) {
        let st = self.ensure_skill(skill_id);
        st.success += 1;
        st.current_stage = AttemptStage::Success;
    }

    pub fn mark_fail(&mut self, skill_id: &str, reason: &str) {
        let st = self.ensure_skill(skill_id);
        st.fail += 1;
        *st.fail_by_reason.entry(reason.to_string()).or_insert(0) += 1;
        st.current_stage = AttemptStage::Failed;
    }

    pub fn mark_stopped(&mut self, skill_id: &str) {
        self.ensure_skill(skill_id).current_stage = AttemptStage::Stopped;
    }

    // ---- metric reset ----

    pub fn reset_metric(&mut self, skill_id: &str, metric: &SkillMetric) {
        let st = self.ensure_skill(skill_id);
        match metric {
            SkillMetric::Success => st.success = 0,
            SkillMetric::AttemptStarted => st.attempt_started = 0,
            SkillMetric::KeySentOk => st.key_sent_ok = 0,
            SkillMetric::CastStarted => st.cast_started = 0,
            SkillMetric::Fail => {
                st.fail = 0;
                st.fail_by_reason.clear();
            }
        }
    }

    pub fn record_timer(&mut self, timer_id: &str, now_ms: u64) {
        let tid = timer_id.trim();
        if !tid.is_empty() {
            self.timers.insert(tid.to_string(), now_ms);
        }
    }

    pub fn reset_timer(&mut self, timer_id: &str) {
        self.timers.remove(timer_id.trim());
    }

    pub fn elapsed_timer_ms(&self, timer_id: &str) -> Option<u64> {
        let started_at = self.timers.get(timer_id.trim())?;
        Some(self.now_ms.saturating_sub(*started_at))
    }

    pub fn set_marker(&mut self, marker_id: &str, value: &str) {
        let mid = marker_id.trim();
        if !mid.is_empty() {
            self.markers.insert(mid.to_string(), value.to_string());
        }
    }

    pub fn clear_marker(&mut self, marker_id: &str) {
        self.markers.remove(marker_id.trim());
    }

    pub fn marker(&self, marker_id: &str) -> Option<&str> {
        self.markers.get(marker_id.trim()).map(String::as_str)
    }

    pub fn set_counter(&mut self, counter_id: &str, value: i64) {
        let cid = counter_id.trim();
        if !cid.is_empty() {
            self.counters.insert(cid.to_string(), value);
        }
    }

    pub fn increment_counter(&mut self, counter_id: &str, by: i64) {
        let cid = counter_id.trim();
        if !cid.is_empty() {
            *self.counters.entry(cid.to_string()).or_insert(0) += by;
        }
    }

    pub fn reset_counter(&mut self, counter_id: &str) {
        self.counters.remove(counter_id.trim());
    }

    pub fn counter(&self, counter_id: &str) -> Option<i64> {
        self.counters.get(counter_id.trim()).copied()
    }
}

// ---------------------------------------------------------------------------
// MetricProvider impl
// ---------------------------------------------------------------------------

impl crate::ast::evaluator::MetricProvider for RuntimeState {
    fn get_metric(&self, skill_id: &str, metric: &SkillMetric) -> Option<u32> {
        let st = self.skills.get(skill_id.trim())?;
        match metric {
            SkillMetric::Success => Some(st.success),
            SkillMetric::AttemptStarted => Some(st.attempt_started),
            SkillMetric::KeySentOk => Some(st.key_sent_ok),
            SkillMetric::CastStarted => Some(st.cast_started),
            SkillMetric::Fail => Some(st.fail),
        }
    }
}

impl crate::ast::evaluator::TimerProvider for RuntimeState {
    fn get_timer_elapsed_ms(&self, timer_id: &str) -> Option<u64> {
        self.elapsed_timer_ms(timer_id)
    }
}

impl crate::ast::evaluator::MarkerProvider for RuntimeState {
    fn get_marker(&self, marker_id: &str) -> Option<&str> {
        self.marker(marker_id)
    }
}

impl crate::ast::evaluator::CounterProvider for RuntimeState {
    fn get_counter(&self, counter_id: &str) -> Option<i64> {
        self.counter(counter_id)
    }
}

// ===========================================================================
// 测试
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_lifecycle() {
        let mut rt = RuntimeState::new();
        rt.engine_started("preset_1");
        assert!(rt.engine.running);
        assert_eq!(rt.engine.preset_id, "preset_1");

        rt.engine_paused();
        assert!(rt.engine.paused);

        rt.engine_resumed();
        assert!(!rt.engine.paused);

        rt.engine_stopped("user_stop");
        assert!(!rt.engine.running);
        assert_eq!(rt.engine.stop_reason, "user_stop");
    }

    #[test]
    fn test_skill_metrics_accumulate() {
        let mut rt = RuntimeState::new();
        rt.mark_attempt_started("sk1");
        rt.mark_key_sent_ok("sk1");
        rt.mark_cast_started("sk1");
        rt.mark_success("sk1");

        let st = rt.skills.get("sk1").unwrap();
        assert_eq!(st.attempt_started, 1);
        assert_eq!(st.key_sent_ok, 1);
        assert_eq!(st.cast_started, 1);
        assert_eq!(st.success, 1);
        assert_eq!(st.fail, 0);
    }

    #[test]
    fn test_skill_metrics_fail() {
        let mut rt = RuntimeState::new();
        rt.mark_fail("sk1", "timeout");
        rt.mark_fail("sk1", "timeout");
        rt.mark_fail("sk1", "send_key_failed");

        let st = rt.skills.get("sk1").unwrap();
        assert_eq!(st.fail, 3);
        assert_eq!(st.fail_by_reason.get("timeout"), Some(&2));
        assert_eq!(st.fail_by_reason.get("send_key_failed"), Some(&1));
    }

    #[test]
    fn test_reset_metric() {
        let mut rt = RuntimeState::new();
        rt.mark_success("sk1");
        rt.mark_success("sk1");
        rt.mark_fail("sk1", "x");

        rt.reset_metric("sk1", &SkillMetric::Success);
        let st = rt.skills.get("sk1").unwrap();
        assert_eq!(st.success, 0);
        assert_eq!(st.fail, 1); // fail untouched
    }

    #[test]
    fn test_metric_provider() {
        use crate::ast::evaluator::MetricProvider as _;
        let mut rt = RuntimeState::new();
        rt.mark_success("sk1");
        rt.mark_success("sk1");
        rt.mark_attempt_started("sk1");

        assert_eq!(rt.get_metric("sk1", &SkillMetric::Success), Some(2));
        assert_eq!(rt.get_metric("sk1", &SkillMetric::AttemptStarted), Some(1));
        assert_eq!(rt.get_metric("sk1", &SkillMetric::Fail), Some(0));
        assert_eq!(rt.get_metric("nonexistent", &SkillMetric::Success), None);
    }

    #[test]
    fn test_timer_provider_elapsed() {
        use crate::ast::evaluator::TimerProvider as _;

        let mut rt = RuntimeState::new();
        rt.record_timer("burst", 1_000);
        rt.set_now_ms(3_500);

        assert_eq!(rt.get_timer_elapsed_ms("burst"), Some(2_500));
        assert_eq!(rt.get_timer_elapsed_ms("missing"), None);

        rt.reset_timer("burst");
        assert_eq!(rt.get_timer_elapsed_ms("burst"), None);
    }

    #[test]
    fn test_marker_provider() {
        use crate::ast::evaluator::MarkerProvider as _;

        let mut rt = RuntimeState::new();
        rt.set_marker("weapon", "main");

        assert_eq!(rt.get_marker("weapon"), Some("main"));
        rt.set_marker("weapon", "alt");
        assert_eq!(rt.get_marker("weapon"), Some("alt"));

        rt.clear_marker("weapon");
        assert_eq!(rt.get_marker("weapon"), None);
    }

    #[test]
    fn test_counter_provider() {
        use crate::ast::evaluator::CounterProvider as _;

        let mut rt = RuntimeState::new();
        rt.set_counter("main_wp2_count", 1);
        assert_eq!(rt.get_counter("main_wp2_count"), Some(1));

        rt.increment_counter("main_wp2_count", 2);
        assert_eq!(rt.get_counter("main_wp2_count"), Some(3));

        rt.reset_counter("main_wp2_count");
        assert_eq!(rt.get_counter("main_wp2_count"), None);
    }
}
