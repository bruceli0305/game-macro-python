// 与 Rust ast/nodes.rs 对齐

export type SkillMetric = "success" | "attempt_started" | "key_sent_ok" | "cast_started" | "fail";

export type Expr =
  | { type: "and"; children: Expr[] }
  | { type: "or"; children: Expr[] }
  | { type: "not"; child: Expr }
  | { type: "const"; value: boolean }
  | { type: "pixel_point"; point_id: string; tolerance: number }
  | { type: "pixel_skill"; skill_id: string; tolerance: number }
  | { type: "cast_bar_changed"; point_id: string; tolerance: number }
  | { type: "skill_metric_ge"; skill_id: string; metric: SkillMetric; count: number };
