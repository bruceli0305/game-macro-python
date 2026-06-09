// 与 Rust ast/nodes.rs 对齐

export type SkillMetric = "success" | "attempt_started" | "key_sent_ok" | "cast_started" | "fail";

export type Expr =
  | { type: "and"; children: Expr[] }
  | { type: "or"; children: Expr[] }
  | { type: "not"; child: Expr }
  | { type: "const"; value: boolean }
  | { type: "pixel_point"; point_id: string; tolerance: number }
  | { type: "pixel_point_not_match"; point_id: string; tolerance: number }
  | { type: "pixel_point_black"; point_id: string; tolerance: number }
  | { type: "pixel_point_not_black"; point_id: string; tolerance: number }
  | { type: "pixel_skill"; skill_id: string; tolerance: number }
  | { type: "pixel_skill_not_match"; skill_id: string; tolerance: number }
  | { type: "pixel_skill_black"; skill_id: string; tolerance: number }
  | { type: "pixel_skill_not_black"; skill_id: string; tolerance: number }
  | { type: "cast_bar_changed"; point_id: string; tolerance: number }
  | { type: "cast_bar_roi_changed" }
  | { type: "cast_bar_roi_border_visible" }
  | { type: "cast_bar_roi_gone" }
  | { type: "skill_metric_ge"; skill_id: string; metric: SkillMetric; count: number }
  | { type: "marker_eq"; marker_id: string; value: string }
  | { type: "marker_ne"; marker_id: string; value: string }
  | { type: "timer_elapsed_ge"; timer_id: string; ms: number }
  | { type: "timer_elapsed_lt"; timer_id: string; ms: number }
  | { type: "counter_ge"; counter_id: string; value: number }
  | { type: "counter_eq"; counter_id: string; value: number }
  | { type: "counter_gt"; counter_id: string; value: number };
