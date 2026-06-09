//! 鎶€鑳藉皾璇曠姸鎬佹満
//!
//! 瀵归綈 python-legacy/rotation_editor/core/runtime/executor/skill_attempt.py
//!
//! 鐘舵€佽浆绉?
//! ```text
//! READY_CHECK 鈹€鈹€false鈹€鈹€鈫?SKIPPED_NOT_READY
//!      鈹?true
//!      鈻?//! Lock acquire 鈹€鈹€busy鈹€鈹€鈫?SKIPPED_LOCK_BUSY (or WAIT_LOCK)
//!      鈹?ok
//!      鈻?//! PREPARING 鈫?send_key
//!      鈹?ok                      鈹?fail
//!      鈻?                        鈻?//! START_WAIT (poll start_expr)  FAILED(send_key_failed)
//!      鈹?true          鈹?timeout
//!      鈻?              鈻?//! CASTING          FAILED(no_cast_start) or retry
//!      鈹?//! COMPLETE_WAIT (poll complete_expr or timer)
//!      鈹?true          鈹?timeout(HYBRID_ASSUME鈫抰rue)
//!      鈻?              鈻?//!   SUCCESS         FAILED(timeout)
//! ```

use crate::ast::evaluator::{
    BaselineProvider, CastBarRoiProvider, EvalContext, MetricProvider, PixelSampler, TriBool,
    evaluate,
};
use crate::ast::nodes::Expr;
use crate::models::base::CastBarRoiConfig;
use crate::models::point::Point;
use crate::models::skill::Skill;

// ---------------------------------------------------------------------------
// ExecutionResult 鈥?缁熶竴杩斿洖鍊?// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecutionResult {
    pub outcome: Outcome,
    pub advance: Advance,
    pub next_delay_ms: u32,
    pub reason: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    Success,
    Failed,
    SkippedNotReady,
    SkippedDisabled,
    SkippedLockBusy,
    Stopped,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Advance {
    Advance,
    Hold,
    NextPhase,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AttemptEvent {
    AttemptStarted { skill_id: String },
    KeySentOk { skill_id: String },
    CastStarted { skill_id: String },
    CompleteWaitStarted { skill_id: String },
    Succeeded { skill_id: String },
    Failed { skill_id: String, reason: String },
    Stopped { skill_id: String },
}

impl ExecutionResult {
    pub fn success(delay_ms: u32, reason: &str) -> Self {
        Self {
            outcome: Outcome::Success,
            advance: Advance::Advance,
            next_delay_ms: delay_ms,
            reason: reason.into(),
        }
    }

    pub fn failed(advance: Advance, delay_ms: u32, reason: &str) -> Self {
        Self {
            outcome: Outcome::Failed,
            advance,
            next_delay_ms: delay_ms,
            reason: reason.into(),
        }
    }

    pub fn skipped_not_ready(delay_ms: u32, reason: &str) -> Self {
        Self {
            outcome: Outcome::SkippedNotReady,
            advance: Advance::Advance,
            next_delay_ms: delay_ms,
            reason: reason.into(),
        }
    }

    pub fn skipped_disabled(delay_ms: u32) -> Self {
        Self {
            outcome: Outcome::SkippedDisabled,
            advance: Advance::Advance,
            next_delay_ms: delay_ms,
            reason: "disabled".into(),
        }
    }

    pub fn skipped_lock_busy(delay_ms: u32) -> Self {
        Self {
            outcome: Outcome::SkippedLockBusy,
            advance: Advance::Hold,
            next_delay_ms: delay_ms,
            reason: "lock_busy".into(),
        }
    }

    pub fn stopped() -> Self {
        Self {
            outcome: Outcome::Stopped,
            advance: Advance::Hold,
            next_delay_ms: 0,
            reason: "stopped".into(),
        }
    }
}

// ---------------------------------------------------------------------------
// 閰嶇疆
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct SkillAttemptConfig {
    pub default_gap_ms: u32,
    pub poll_not_ready_ms: u32,
    /// Max lock wait before sending a key. Zero means skip when busy.
    pub lock_wait_timeout_ms: u32,
    pub lock_wait_poll_ms: u32,
    /// START 闃舵
    pub start_timeout_ms: u32,
    pub start_poll_ms: u32,
    pub max_retries: u32,
    pub retry_gap_ms: u32,
    pub failure_policy: AttemptFailurePolicy,
    /// COMPLETE 闃舵
    pub complete_policy: CompletePolicy,
    pub complete_poll_ms: u32,
    pub complete_timeout_ms: Option<u32>,
    pub complete_max_wait_factor: f64,
    pub cast_bar_roi: Option<CastBarRoiConfig>,
    /// 浜嬩欢鑺傛祦
    pub sample_log_throttle_ms: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AttemptFailurePolicy {
    NextSlot,
    HoldPhase,
    NextPhase,
}

impl AttemptFailurePolicy {
    pub fn advance(self) -> Advance {
        match self {
            Self::NextSlot => Advance::Advance,
            Self::HoldPhase => Advance::Hold,
            Self::NextPhase => Advance::NextPhase,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompletePolicy {
    /// 浠呮寜璇绘潯鏃堕棿绛夊緟锛屽埌鏃跺嵆鎴愬姛
    AssumeSuccess,
    /// 蹇呴』鐪嬪埌 complete_expr 涓?True
    RequireSignal,
    /// 鏈変俊鍙锋椂涓ユ牸鏍￠獙锛岃秴鏃跺悗鍋囧畾鎴愬姛
    HybridAssume,
    /// Treat timeout as failure.
    HybridFail,
    /// 鎶€鑳藉儚绱?鍙橀粦"纭杩涘叆鍐峰嵈
    CdBlack,
}

impl Default for SkillAttemptConfig {
    fn default() -> Self {
        Self {
            default_gap_ms: 50,
            poll_not_ready_ms: 50,
            lock_wait_timeout_ms: 0,
            lock_wait_poll_ms: 5,
            start_timeout_ms: 20,
            start_poll_ms: 10,
            max_retries: 3,
            retry_gap_ms: 30,
            failure_policy: AttemptFailurePolicy::NextSlot,
            complete_policy: CompletePolicy::AssumeSuccess,
            complete_poll_ms: 30,
            complete_timeout_ms: None,
            complete_max_wait_factor: 1.5,
            cast_bar_roi: None,
            sample_log_throttle_ms: 80,
        }
    }
}

// ---------------------------------------------------------------------------
// KeySender trait 鈥?鍙戦敭鎶借薄
// ---------------------------------------------------------------------------

pub trait KeySender: Send + Sync {
    fn send_key(&mut self, key: &str) -> bool;
}

pub struct SkillAttemptRequest<'a> {
    pub skill_id: &'a str,
    pub readbar_ms: u32,
    pub ready_expr: Option<&'a Expr>,
    pub start_expr: Option<&'a Expr>,
    pub complete_expr: Option<&'a Expr>,
}

// ---------------------------------------------------------------------------
// SkillAttemptExecutor
// ---------------------------------------------------------------------------

pub struct SkillAttemptExecutor<'a> {
    pub points: &'a [Point],
    pub skills: &'a [Skill],
    pub sampler: &'a dyn PixelSampler,
    pub metrics: Option<&'a dyn MetricProvider>,
    pub baseline: Option<&'a dyn BaselineProvider>,
    pub cast_bar_roi: Option<&'a dyn CastBarRoiProvider>,
    pub cfg: SkillAttemptConfig,
}

impl<'a> SkillAttemptExecutor<'a> {
    pub fn new(
        points: &'a [Point],
        skills: &'a [Skill],
        sampler: &'a dyn PixelSampler,
        cfg: SkillAttemptConfig,
    ) -> Self {
        Self {
            points,
            skills,
            sampler,
            metrics: None,
            baseline: None,
            cast_bar_roi: None,
            cfg,
        }
    }

    fn make_ctx(&'a self) -> EvalContext<'a> {
        EvalContext {
            points: self.points,
            skills: self.skills,
            sampler: self.sampler,
            metrics: self.metrics,
            timers: None,
            markers: None,
            counters: None,
            baseline: self.baseline,
            cast_bar_roi: self.cast_bar_roi,
        }
    }

    /// Execute one skill attempt.
    pub fn exec_skill_node(
        &self,
        key_sender: &mut dyn KeySender,
        request: SkillAttemptRequest,
        stopped: &dyn Fn() -> bool,
    ) -> ExecutionResult {
        self.exec_skill_node_with_events(key_sender, request, stopped, &mut |_| {})
    }

    pub fn exec_skill_node_with_events(
        &self,
        key_sender: &mut dyn KeySender,
        request: SkillAttemptRequest,
        stopped: &dyn Fn() -> bool,
        events: &mut dyn FnMut(AttemptEvent),
    ) -> ExecutionResult {
        let sid = request.skill_id.trim();
        if sid.is_empty() {
            return ExecutionResult::failed(Advance::Advance, 50, "skill_id_empty");
        }

        // ---- 鏌ユ壘鎶€鑳?----
        let skill = match self.skills.iter().find(|s| s.id.as_str() == sid) {
            Some(s) => s,
            None => return ExecutionResult::failed(Advance::Advance, 50, "skill_missing"),
        };

        if !skill.enabled {
            return ExecutionResult::skipped_disabled(self.cfg.poll_not_ready_ms);
        }

        if stopped() {
            events(AttemptEvent::Stopped {
                skill_id: sid.to_string(),
            });
            return ExecutionResult::stopped();
        }

        events(AttemptEvent::AttemptStarted {
            skill_id: sid.to_string(),
        });

        // ---- READY_CHECK ----
        let ready_e = request.ready_expr.unwrap_or(&READY_DEFAULT);
        let ctx = self.make_ctx();
        let ready_tri = evaluate(ready_e, &ctx);
        if !ready_tri.is_true() {
            let reason = match &ready_tri {
                TriBool::False(r) => r.clone(),
                TriBool::Unknown(r) => r.clone(),
                _ => "not_ready".into(),
            };
            return ExecutionResult::skipped_not_ready(self.cfg.poll_not_ready_ms, &reason);
        }

        // ---- 鍙戦敭 ----
        if !key_sender.send_key(&skill.trigger_key) {
            events(AttemptEvent::Failed {
                skill_id: sid.to_string(),
                reason: "send_key_failed".into(),
            });
            return ExecutionResult::failed(
                Advance::Advance,
                self.cfg.poll_not_ready_ms,
                "send_key_failed",
            );
        }
        events(AttemptEvent::KeySentOk {
            skill_id: sid.to_string(),
        });

        if stopped() {
            events(AttemptEvent::Stopped {
                skill_id: sid.to_string(),
            });
            return ExecutionResult::stopped();
        }

        let readbar = request.readbar_ms.max(1);

        // ---- START_WAIT ----
        let start_e = request.start_expr.unwrap_or(&START_DEFAULT);
        let mut retries_left = self.cfg.max_retries;

        loop {
            if stopped() {
                events(AttemptEvent::Stopped {
                    skill_id: sid.to_string(),
                });
                return ExecutionResult::stopped();
            }

            // 妫€鏌?start 淇″彿
            if self.poll_expr_until(
                start_e,
                self.cfg.start_timeout_ms,
                self.cfg.start_poll_ms,
                stopped,
            ) {
                break;
            }

            if retries_left > 0 {
                retries_left -= 1;
                if !key_sender.send_key(&skill.trigger_key) {
                    events(AttemptEvent::Failed {
                        skill_id: sid.to_string(),
                        reason: "send_key_failed_retry".into(),
                    });
                    return ExecutionResult::failed(
                        Advance::Advance,
                        self.cfg.poll_not_ready_ms,
                        "send_key_failed_retry",
                    );
                }
                events(AttemptEvent::KeySentOk {
                    skill_id: sid.to_string(),
                });
                // 璋冪敤鏂硅礋璐?sleep(retry_gap_ms)
                continue;
            }

            events(AttemptEvent::Failed {
                skill_id: sid.to_string(),
                reason: "no_cast_start".into(),
            });
            return ExecutionResult::failed(
                Advance::Advance,
                self.cfg.poll_not_ready_ms,
                "no_cast_start",
            );
        }

        events(AttemptEvent::CastStarted {
            skill_id: sid.to_string(),
        });

        if stopped() {
            events(AttemptEvent::Stopped {
                skill_id: sid.to_string(),
            });
            return ExecutionResult::stopped();
        }

        // ---- COMPLETE_WAIT ----
        events(AttemptEvent::CompleteWaitStarted {
            skill_id: sid.to_string(),
        });
        let ok = match self.cfg.complete_policy {
            CompletePolicy::AssumeSuccess => true,
            CompletePolicy::CdBlack => self.poll_cd_black(skill, readbar, stopped),
            _ => {
                let complete_e = match request.complete_expr {
                    Some(e) => e,
                    None => {
                        if self.cfg.complete_policy == CompletePolicy::HybridAssume {
                            events(AttemptEvent::Succeeded {
                                skill_id: sid.to_string(),
                            });
                            return ExecutionResult::success(
                                self.cfg.default_gap_ms,
                                "hybrid_assume_no_expr",
                            );
                        }
                        events(AttemptEvent::Failed {
                            skill_id: sid.to_string(),
                            reason: "complete_signal_missing".into(),
                        });
                        return ExecutionResult::failed(
                            Advance::Advance,
                            self.cfg.poll_not_ready_ms,
                            "complete_signal_missing",
                        );
                    }
                };
                let max_wait = (readbar as f64 * self.cfg.complete_max_wait_factor) as u32;
                let got_signal =
                    self.poll_expr_until(complete_e, max_wait, self.cfg.complete_poll_ms, stopped);
                match self.cfg.complete_policy {
                    CompletePolicy::RequireSignal if !got_signal => {
                        events(AttemptEvent::Failed {
                            skill_id: sid.to_string(),
                            reason: "timeout".into(),
                        });
                        return ExecutionResult::failed(
                            Advance::Advance,
                            self.cfg.poll_not_ready_ms,
                            "timeout",
                        );
                    }
                    CompletePolicy::HybridFail if !got_signal => {
                        events(AttemptEvent::Failed {
                            skill_id: sid.to_string(),
                            reason: "timeout".into(),
                        });
                        return ExecutionResult::failed(
                            Advance::Advance,
                            self.cfg.poll_not_ready_ms,
                            "timeout",
                        );
                    }
                    _ => got_signal, // HybridAssume: true even on timeout
                }
            }
        };

        if stopped() {
            events(AttemptEvent::Stopped {
                skill_id: sid.to_string(),
            });
            return ExecutionResult::stopped();
        }

        if ok {
            events(AttemptEvent::Succeeded {
                skill_id: sid.to_string(),
            });
            ExecutionResult::success(self.cfg.default_gap_ms, "success")
        } else {
            events(AttemptEvent::Failed {
                skill_id: sid.to_string(),
                reason: "complete_failed".into(),
            });
            ExecutionResult::failed(
                Advance::Advance,
                self.cfg.poll_not_ready_ms,
                "complete_failed",
            )
        }
    }

    /// 杞琛ㄨ揪寮忕洿鍒颁负 True 鎴栬秴鏃躲€俿topped 鍥炶皟鍦ㄤ笂灞傚仛 sleep/wait
    fn poll_expr_until(
        &self,
        expr: &Expr,
        _timeout_ms: u32,
        _poll_ms: u32,
        stopped: &dyn Fn() -> bool,
    ) -> bool {
        if stopped() {
            return false;
        }
        let ctx = self.make_ctx();
        evaluate(expr, &ctx).is_true()
    }

    /// Check whether the skill icon is close to black.
    fn poll_cd_black(&self, skill: &Skill, _readbar_ms: u32, stopped: &dyn Fn() -> bool) -> bool {
        if stopped() {
            return false;
        }
        let pix = &skill.pixel;
        match self.sampler.sample_rgb_abs(
            &pix.monitor,
            pix.vx,
            pix.vy,
            &pix.sample.mode,
            pix.sample.radius,
        ) {
            None => false,
            Some((r, g, b)) => {
                let diff = r.max(g).max(b);
                diff <= 5
            }
        }
    }

    /// Return the configured tolerance for a skill pixel.
    pub fn tol_from_skill_pixel(&self, skill_id: &str) -> u8 {
        self.skills
            .iter()
            .find(|s| s.id.as_str() == skill_id.trim())
            .map(|s| s.pixel.tolerance)
            .unwrap_or(0)
    }
}

// ---- 榛樿琛ㄨ揪寮忥紙缂栬瘧鏃舵瀯寤烘垨娴嬭瘯鐢ㄥ崰浣嶏級 ----
// 瀹為檯浣跨敤鏃剁敱寮曟搸浼犲叆缂栬瘧濂界殑 Expr

/// Default ready expression used when the engine does not provide one.
pub static READY_DEFAULT: Expr = Expr::Const { value: true };

/// Default start expression used when the engine does not provide one.
pub static START_DEFAULT: Expr = Expr::Const { value: true };

// ===========================================================================
// 娴嬭瘯
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::evaluator::PixelSampler;
    use crate::models::point::Point;
    use crate::models::skill::{ColorRGB, PixelSpec, SampleConfig, Skill};

    // ---- 娴嬭瘯鏇胯韩 ----

    struct DummySampler {
        rgb: (u8, u8, u8),
    }
    impl PixelSampler for DummySampler {
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

    struct DummyKeySender {
        pub should_fail: bool,
        pub keys_sent: Vec<String>,
    }
    impl KeySender for DummyKeySender {
        fn send_key(&mut self, key: &str) -> bool {
            self.keys_sent.push(key.to_string());
            !self.should_fail
        }
    }

    fn make_skill(id: &str, key: &str, r: u8, g: u8, b: u8, enabled: bool) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            enabled,
            trigger_key: key.into(),
            cast: Default::default(),
            pixel: PixelSpec {
                monitor: "primary".into(),
                vx: 0,
                vy: 0,
                color: ColorRGB { r, g, b },
                tolerance: 10,
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

    fn make_test_env(
        rgb: (u8, u8, u8),
    ) -> (Vec<Point>, Vec<Skill>, DummySampler, SkillAttemptConfig) {
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1", rgb.0, rgb.1, rgb.2, true)];
        let sampler = DummySampler { rgb };
        let cfg = SkillAttemptConfig {
            complete_policy: CompletePolicy::AssumeSuccess,
            ..Default::default()
        };
        (points, skills, sampler, cfg)
    }

    fn request(skill_id: &str) -> SkillAttemptRequest<'_> {
        SkillAttemptRequest {
            skill_id,
            readbar_ms: 100,
            ready_expr: None,
            start_expr: None,
            complete_expr: None,
        }
    }

    #[test]
    fn test_missing_skill() {
        let (points, skills, sampler, cfg) = make_test_env((100, 150, 200));
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: false,
            keys_sent: vec![],
        };
        let res = exec.exec_skill_node(&mut ks, request("nonexistent"), &|| false);
        assert_eq!(res.outcome, Outcome::Failed);
        assert!(res.reason.contains("skill_missing"));
    }

    #[test]
    fn test_disabled_skill() {
        let points = vec![];
        let skills = vec![make_skill("sk1", "f1", 100, 150, 200, false)];
        let sampler = DummySampler {
            rgb: (100, 150, 200),
        };
        let cfg = SkillAttemptConfig::default();
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: false,
            keys_sent: vec![],
        };
        let res = exec.exec_skill_node(&mut ks, request("sk1"), &|| false);
        assert_eq!(res.outcome, Outcome::SkippedDisabled);
    }

    #[test]
    fn test_send_key_failure() {
        let (points, skills, sampler, cfg) = make_test_env((100, 150, 200));
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: true,
            keys_sent: vec![],
        };
        let res = exec.exec_skill_node(&mut ks, request("sk1"), &|| false);
        assert_eq!(res.outcome, Outcome::Failed);
        assert!(res.reason.contains("send_key_failed"));
    }

    #[test]
    fn test_success_assume() {
        let (points, skills, sampler, cfg) = make_test_env((100, 150, 200));
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: false,
            keys_sent: vec![],
        };
        let res = exec.exec_skill_node(&mut ks, request("sk1"), &|| false);
        assert_eq!(res.outcome, Outcome::Success);
        assert_eq!(ks.keys_sent, vec!["f1"]);
    }

    #[test]
    fn test_events_distinguish_retry_without_cast_start() {
        let (points, skills, sampler, mut cfg) = make_test_env((100, 150, 200));
        cfg.max_retries = 2;
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: false,
            keys_sent: vec![],
        };
        let start_expr = Expr::Const { value: false };
        let mut events = Vec::new();

        let res = exec.exec_skill_node_with_events(
            &mut ks,
            SkillAttemptRequest {
                start_expr: Some(&start_expr),
                ..request("sk1")
            },
            &|| false,
            &mut |event| events.push(event),
        );

        assert_eq!(res.outcome, Outcome::Failed);
        assert_eq!(res.reason, "no_cast_start");
        assert_eq!(ks.keys_sent, vec!["f1", "f1", "f1"]);
        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, AttemptEvent::KeySentOk { .. }))
                .count(),
            3
        );
        assert!(
            !events
                .iter()
                .any(|event| matches!(event, AttemptEvent::CastStarted { .. }))
        );
        assert_eq!(
            events.last(),
            Some(&AttemptEvent::Failed {
                skill_id: "sk1".into(),
                reason: "no_cast_start".into(),
            })
        );
    }

    #[test]
    fn test_stopped_before_send() {
        let (points, skills, sampler, cfg) = make_test_env((100, 150, 200));
        let exec = SkillAttemptExecutor::new(&points, &skills, &sampler, cfg);
        let mut ks = DummyKeySender {
            should_fail: false,
            keys_sent: vec![],
        };
        let res = exec.exec_skill_node(&mut ks, request("sk1"), &|| true);
        assert_eq!(res.outcome, Outcome::Stopped);
    }
}
