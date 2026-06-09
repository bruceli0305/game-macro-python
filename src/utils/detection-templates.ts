import type { Expr } from "../types/ast";

export type StartDetectionTemplate =
  | "none"
  | "immediate"
  | "cast_bar_changed"
  | "cast_bar_roi_changed"
  | "cast_bar_roi_border_visible";

export type CompleteDetectionTemplate =
  | "timer"
  | "cast_bar_changed"
  | "cast_bar_roi_gone"
  | "skill_pixel"
  | "skill_pixel_black";

export const DEFAULT_DETECTION_TOLERANCE = 20;

export function buildStartDetectionExpr(
  template: StartDetectionTemplate,
  pointId = "",
  tolerance = DEFAULT_DETECTION_TOLERANCE
): Expr | null {
  switch (template) {
    case "none":
      return null;
    case "immediate":
      return { type: "const", value: true };
    case "cast_bar_changed":
      return { type: "cast_bar_changed", point_id: pointId, tolerance };
    case "cast_bar_roi_changed":
      return { type: "cast_bar_roi_changed" };
    case "cast_bar_roi_border_visible":
      return { type: "cast_bar_roi_border_visible" };
  }
}

export function buildCompleteDetectionExpr(
  template: CompleteDetectionTemplate,
  skillId = "",
  pointId = "",
  tolerance = DEFAULT_DETECTION_TOLERANCE
): Expr | null {
  switch (template) {
    case "timer":
      return null;
    case "cast_bar_changed":
      return { type: "cast_bar_changed", point_id: pointId, tolerance };
    case "cast_bar_roi_gone":
      return { type: "cast_bar_roi_gone" };
    case "skill_pixel":
      return { type: "pixel_skill", skill_id: skillId, tolerance };
    case "skill_pixel_black":
      return { type: "pixel_skill_black", skill_id: skillId, tolerance };
  }
}

export function firstPointId(points: { id: string }[]): string {
  return points[0]?.id ?? "";
}
