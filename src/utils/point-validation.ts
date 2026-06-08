import type { Point } from "../types/point";

export interface PointDraftValidationContext {
  existingPoints: Point[];
  editingIndex: number;
}

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value);
}

function isByte(value: number): boolean {
  return Number.isInteger(value) && value >= 0 && value <= 255;
}

function clampByte(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(255, Math.max(0, Math.round(value)));
}

export function validatePointDraft(
  point: Point,
  context: PointDraftValidationContext
): string | null {
  const pointId = point.id.trim();
  if (!pointId) return "点位 ID 不能为空";
  if (!point.name.trim()) return "点位名称不能为空";

  const duplicateIndex = context.existingPoints.findIndex(
    (item, index) => index !== context.editingIndex && item.id.trim() === pointId
  );
  if (duplicateIndex >= 0) return `点位 ID 重复：${pointId}`;

  if (!isFiniteNumber(point.vx) || !isFiniteNumber(point.vy)) {
    return `点位坐标必须是有效数字：${point.name.trim() || pointId}`;
  }

  if (!Number.isInteger(point.tolerance) || point.tolerance < 0 || point.tolerance > 255) {
    return `点位容差必须在 0-255 之间：${point.name.trim() || pointId}`;
  }

  if (!isByte(point.color.r) || !isByte(point.color.g) || !isByte(point.color.b)) {
    return `点位颜色必须是 0-255 的 RGB 值：${point.name.trim() || pointId}`;
  }

  if (!Number.isInteger(point.sample.radius) || point.sample.radius < 0 || point.sample.radius > 255) {
    return `点位采样半径必须在 0-255 之间：${point.name.trim() || pointId}`;
  }

  const sampleMode = point.sample.mode.trim();
  if (sampleMode !== "single" && sampleMode !== "mean_square") {
    return `点位采样模式必须是 single 或 mean_square：${point.name.trim() || pointId}`;
  }

  return null;
}

export function normalizePointDraft(point: Point): Point {
  return {
    ...point,
    id: point.id.trim(),
    name: point.name.trim(),
    monitor: point.monitor.trim() || "primary",
    vx: Math.round(point.vx),
    vy: Math.round(point.vy),
    color: {
      r: clampByte(point.color.r),
      g: clampByte(point.color.g),
      b: clampByte(point.color.b),
    },
    tolerance: clampByte(point.tolerance),
    sample: {
      ...point.sample,
      mode: point.sample.mode.trim() || "single",
      radius: clampByte(point.sample.radius),
    },
    note: point.note.trim(),
  };
}

export function firstPointDraftError(points: Point[]): string | null {
  for (const [index, point] of points.entries()) {
    const error = validatePointDraft(point, {
      existingPoints: points,
      editingIndex: index,
    });
    if (error) return error;
  }
  return null;
}
