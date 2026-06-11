// 与 Rust models/cycle.rs 对齐

export interface CycleConfig {
  name: string;
  phases: CyclePhase[];
  observer_lanes?: ObserverLaneConfig[];
  assist_lanes?: AssistLaneConfig[];
  poll_interval_ms: number;
  max_cycles: number;
  state_schema?: CycleStateSchema | null;
}

export interface ObserverLaneConfig {
  id: string;
  name: string;
  enabled: boolean;
  check_interval_ms: number;
  actions: ObserverActionSlot[];
}

export interface ObserverActionSlot {
  id: string;
  label: string;
  priority: number;
  condition_expr: Record<string, unknown> | null;
  actions: RuntimeAction[];
}

export interface AssistLaneConfig {
  id: string;
  name: string;
  enabled: boolean;
  check_interval_ms: number;
  interrupt_policy: AssistInterruptPolicy;
  skills: SkillSlot[];
}

export type AssistInterruptPolicy = "idle_only" | "complete_wait" | "any_wait";

export interface CyclePhase {
  name: string;
  skills: SkillSlot[];
  complete_when: "all_fired" | "any_fired" | "always" | "none_ready";
  entry_actions?: RuntimeAction[];
  transition_rules?: PhaseTransitionRule[];
  fallback_transition?: PhaseFallbackTransition | null;
}

export interface PhaseTransitionRule {
  label: string;
  condition_expr: Record<string, unknown> | null;
  target_phase: string;
}

export type PhaseFallbackTransition =
  | { type: "stay" }
  | { type: "next" }
  | { type: "phase"; target_phase: string };

export interface SkillSlot {
  skill_id: string;
  priority: number;
  label: string;
  slot_role?: SkillSlotRole;
  condition_expr: Record<string, unknown> | null;
  readiness_expr?: Record<string, unknown> | null;
  readiness_policy?: ReadinessPolicy;
  start_expr: Record<string, unknown> | null;
  complete_expr: Record<string, unknown> | null;
  override_cast_ms: number | null;
  protected_release?: boolean;
  attempt_policy?: AttemptPolicy | null;
  post_actions?: RuntimeAction[];
}

export type SkillSlotRole = "mandatory" | "priority" | "filler";

export type ReadinessPolicy = "required" | "advisory";

export interface AttemptPolicy {
  max_attempts: number;
  start_timeout_ms: number;
  complete_timeout_ms: number;
  retry_delay_ms: number;
  failure_policy: "hold_phase" | "next_slot" | "next_phase";
  complete_fallback: "fail" | "assume_success_after_timeout";
}

export interface CycleStateSchema {
  markers: RuntimeMarkerDef[];
  timers: RuntimeTimerDef[];
  counters: RuntimeCounterDef[];
}

export interface RuntimeMarkerDef {
  id: string;
  name: string;
  initial_value: string;
  allowed_values: string[];
}

export interface RuntimeTimerDef {
  id: string;
  name: string;
  reset_on_cycle_start: boolean;
}

export interface RuntimeCounterDef {
  id: string;
  name: string;
  initial_value: number;
  reset_on_phase_entry: boolean;
  reset_on_cycle_start: boolean;
}

export type RuntimeAction =
  | { type: "set_marker"; marker_id: string; value: string }
  | { type: "clear_marker"; marker_id: string }
  | { type: "record_timer"; timer_id: string }
  | { type: "reset_timer"; timer_id: string }
  | { type: "increment_counter"; counter_id: string; by: number }
  | { type: "set_counter"; counter_id: string; value: number }
  | { type: "reset_counter"; counter_id: string };
