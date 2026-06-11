//! Runtime action application for `CycleExecutor`.

use crate::engine::cycle_executor::{CycleExecutor, CycleLogEvent};
use crate::models::cycle::RuntimeAction;

impl<'a> CycleExecutor<'a> {
    pub(super) fn apply_runtime_actions(
        &mut self,
        actions: &[RuntimeAction],
        now_ms: u64,
        phase_idx: usize,
        phase_name: &str,
        skill_id: &str,
    ) {
        for action in actions {
            let reason = match action {
                RuntimeAction::SetMarker { marker_id, value } => {
                    self.runtime.set_marker(marker_id, value);
                    format!("set_marker:{marker_id}={value}")
                }
                RuntimeAction::ClearMarker { marker_id } => {
                    self.runtime.clear_marker(marker_id);
                    format!("clear_marker:{marker_id}")
                }
                RuntimeAction::RecordTimer { timer_id } => {
                    self.runtime.record_timer(timer_id, now_ms);
                    format!("record_timer:{timer_id}")
                }
                RuntimeAction::ResetTimer { timer_id } => {
                    self.runtime.reset_timer(timer_id);
                    format!("reset_timer:{timer_id}")
                }
                RuntimeAction::IncrementCounter { counter_id, by } => {
                    self.runtime.increment_counter(counter_id, *by);
                    format!("increment_counter:{counter_id}+={by}")
                }
                RuntimeAction::SetCounter { counter_id, value } => {
                    self.runtime.set_counter(counter_id, *value);
                    format!("set_counter:{counter_id}={value}")
                }
                RuntimeAction::ResetCounter { counter_id } => {
                    self.reset_counter_to_initial(counter_id);
                    format!("reset_counter:{counter_id}")
                }
            };
            self.log_event(CycleLogEvent {
                ts_ms: now_ms,
                phase_index: phase_idx,
                phase_name,
                event: "runtime_action",
                skill_id,
                outcome: "Applied",
                reason: &reason,
            });
        }
    }

    pub(super) fn reset_phase_entry_counters(&mut self) {
        let Some(schema) = &self.config.state_schema else {
            return;
        };
        for counter in &schema.counters {
            if counter.reset_on_phase_entry {
                self.runtime.set_counter(&counter.id, counter.initial_value);
            }
        }
    }

    fn reset_counter_to_initial(&mut self, counter_id: &str) {
        let counter_id = counter_id.trim();
        if counter_id.is_empty() {
            return;
        }
        let initial_value = self
            .config
            .state_schema
            .as_ref()
            .and_then(|schema| {
                schema
                    .counters
                    .iter()
                    .find(|counter| counter.id == counter_id)
            })
            .map(|counter| counter.initial_value)
            .unwrap_or(0);
        self.runtime.set_counter(counter_id, initial_value);
    }
}
