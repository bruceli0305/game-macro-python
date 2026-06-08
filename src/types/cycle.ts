// 与 Rust models/cycle.rs 对齐

export interface CycleConfig {
  name: string;
  phases: CyclePhase[];
  poll_interval_ms: number;
  max_cycles: number;
}

export interface CyclePhase {
  name: string;
  skills: SkillSlot[];
  complete_when: "all_fired" | "any_fired" | "always" | "none_ready";
}

export interface SkillSlot {
  skill_id: string;
  priority: number;
  label: string;
  condition_expr: Record<string, unknown> | null;
  start_expr: Record<string, unknown> | null;
  complete_expr: Record<string, unknown> | null;
  override_cast_ms: number | null;
}
