//! Per-tick orchestration for `CycleExecutor`.

use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::phase_scanner::PhaseScanOutcome;
use crate::engine::runtime_config::AttemptContext;
use crate::engine::skill_attempt::{AttemptEvent, KeySender};

impl<'a> CycleExecutor<'a> {
    /// Advance the cycle executor by one scheduler tick.
    pub fn tick(
        &mut self,
        key_sender: &mut dyn KeySender,
        stopped: &dyn Fn() -> bool,
        now_ms: u64,
    ) -> bool {
        self.runtime.set_now_ms(now_ms);
        self.sampler.begin_tick(now_ms);
        if let Some(provider) = self.cast_bar_roi {
            provider.begin_tick(now_ms);
        }

        if stopped() {
            if let Some(pending) = self.pending_attempt.take() {
                self.apply_attempt_event(AttemptEvent::Stopped {
                    skill_id: pending.skill_id,
                });
            }
            if let Some(pending) = self.suspended_main_attempt.take() {
                self.apply_attempt_event(AttemptEvent::Stopped {
                    skill_id: pending.skill_id,
                });
            }
            return false;
        }

        self.try_observer_lanes(now_ms);

        if let Some(pending) = self.pending_attempt.take() {
            if matches!(pending.context, AttemptContext::Main { .. })
                && !pending.protected_release
                && self.suspended_main_attempt.is_none()
                && self.try_assist_lanes(key_sender, stopped, now_ms, Some(pending.stage))
            {
                if self.pending_attempt.is_some() {
                    self.suspended_main_attempt = Some(pending);
                } else {
                    self.pending_attempt = Some(pending);
                }
                return true;
            }
            return self.advance_pending_attempt(key_sender, stopped, now_ms, pending);
        }

        match self.scan_active_phase(key_sender, stopped, now_ms) {
            PhaseScanOutcome::Acted => true,
            PhaseScanOutcome::AllowAssist => {
                self.try_assist_lanes(key_sender, stopped, now_ms, None)
            }
            PhaseScanOutcome::Blocked => false,
        }
    }
}
