import type { Profile } from "../types/profile";
import type { Point } from "../types/point";
import type { PixelSpec, SampleConfig } from "../types/skill";

export interface ProfileValidationIssue {
  path: string;
  message: string;
  severity: "error" | "warning";
}

interface ExprRefContext {
  skillIds: Set<string>;
  pointIds: Set<string>;
  issues: ProfileValidationIssue[];
  path: string;
}

function issue(path: string, message: string): ProfileValidationIssue {
  return { path, message, severity: "error" };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeHotkey(value: string): string {
  return value.trim().toUpperCase();
}

function isIntegerInRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value);
}

function isByte(value: number): boolean {
  return Number.isInteger(value) && value >= 0 && value <= 255;
}

function validateSampleConfig(sample: SampleConfig, path: string): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  const mode = sample.mode.trim();
  if (mode !== "single" && mode !== "mean_square") {
    issues.push(issue(`${path}.mode`, "采样模式必须是 single 或 mean_square"));
  }
  if (!Number.isInteger(sample.radius) || sample.radius < 0 || sample.radius > 255) {
    issues.push(issue(`${path}.radius`, "采样半径必须在 0-255 之间"));
  }
  return issues;
}

function validatePixelSpec(pixel: PixelSpec, path: string): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  if (!pixel.monitor.trim()) {
    issues.push(issue(`${path}.monitor`, "像素配置必须指定显示器"));
  }
  if (!isFiniteNumber(pixel.vx) || !isFiniteNumber(pixel.vy)) {
    issues.push(issue(path, "像素坐标必须是有效数字"));
  }
  if (!isByte(pixel.color.r) || !isByte(pixel.color.g) || !isByte(pixel.color.b)) {
    issues.push(issue(`${path}.color`, "像素颜色必须是 0-255 的 RGB 值"));
  }
  if (!isByte(pixel.tolerance)) {
    issues.push(issue(`${path}.tolerance`, "像素容差必须在 0-255 之间"));
  }
  issues.push(...validateSampleConfig(pixel.sample, `${path}.sample`));
  return issues;
}

function validatePointConfig(point: Point, path: string): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  if (!point.name.trim()) {
    issues.push(issue(`${path}.name`, "点位名称不能为空"));
  }
  if (!point.monitor.trim()) {
    issues.push(issue(`${path}.monitor`, "点位必须指定显示器"));
  }
  if (!isFiniteNumber(point.vx) || !isFiniteNumber(point.vy)) {
    issues.push(issue(path, "点位坐标必须是有效数字"));
  }
  if (!isByte(point.color.r) || !isByte(point.color.g) || !isByte(point.color.b)) {
    issues.push(issue(`${path}.color`, "点位颜色必须是 0-255 的 RGB 值"));
  }
  if (!isByte(point.tolerance)) {
    issues.push(issue(`${path}.tolerance`, "点位容差必须在 0-255 之间"));
  }
  issues.push(...validateSampleConfig(point.sample, `${path}.sample`));
  return issues;
}

function validateBaseConfig(profile: Profile): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  const base = profile.base;

  if (!base.capture.monitor_policy.trim()) {
    issues.push(issue("base.capture.monitor_policy", "显示器策略不能为空"));
  }

  if (!base.pick.confirm_hotkey.trim()) {
    issues.push(issue("base.pick.confirm_hotkey", "取色确认热键不能为空"));
  }
  if (!isIntegerInRange(base.pick.mouse_avoid_offset_y, -1000, 1000)) {
    issues.push(issue("base.pick.mouse_avoid_offset_y", "取色避让偏移必须在 -1000 到 1000 之间"));
  }
  if (!isIntegerInRange(base.pick.mouse_avoid_settle_ms, 0, 5000)) {
    issues.push(issue("base.pick.mouse_avoid_settle_ms", "取色避让等待必须在 0-5000ms 之间"));
  }

  const castBarMode = base.cast_bar.mode.trim();
  if (castBarMode !== "timer" && castBarMode !== "pixel") {
    issues.push(issue("base.cast_bar.mode", "读条模式必须是 timer 或 pixel"));
  }
  if (!isByte(base.cast_bar.tolerance)) {
    issues.push(issue("base.cast_bar.tolerance", "读条容差必须在 0-255 之间"));
  }
  if (!isIntegerInRange(base.cast_bar.poll_interval_ms, 1, 10000)) {
    issues.push(issue("base.cast_bar.poll_interval_ms", "读条轮询间隔必须在 1-10000ms 之间"));
  }
  if (
    !Number.isFinite(base.cast_bar.max_wait_factor) ||
    base.cast_bar.max_wait_factor < 0.1 ||
    base.cast_bar.max_wait_factor > 10
  ) {
    issues.push(issue("base.cast_bar.max_wait_factor", "读条最大等待倍率必须在 0.1-10 之间"));
  }

  if (!base.exec.toggle_hotkey.trim()) {
    issues.push(issue("base.exec.toggle_hotkey", "引擎启停热键不能为空"));
  }
  if (!isIntegerInRange(base.exec.default_skill_gap_ms, 0, 10000)) {
    issues.push(issue("base.exec.default_skill_gap_ms", "技能间隔必须在 0-10000ms 之间"));
  }
  if (!isIntegerInRange(base.exec.poll_not_ready_ms, 1, 10000)) {
    issues.push(issue("base.exec.poll_not_ready_ms", "未就绪轮询间隔必须在 1-10000ms 之间"));
  }
  if (!isIntegerInRange(base.exec.max_retries, 0, 20)) {
    issues.push(issue("base.exec.max_retries", "最大重试次数必须在 0-20 之间"));
  }
  if (!isIntegerInRange(base.exec.retry_gap_ms, 0, 10000)) {
    issues.push(issue("base.exec.retry_gap_ms", "重试间隔必须在 0-10000ms 之间"));
  }

  return issues;
}

function validateExprRefs(expr: unknown, ctx: ExprRefContext): void {
  if (expr == null) return;
  if (!isRecord(expr)) {
    ctx.issues.push(issue(ctx.path, "条件表达式必须是对象"));
    return;
  }

  const typ = stringField(expr.type);
  if (!typ) {
    ctx.issues.push(issue(ctx.path, "条件表达式缺少 type"));
    return;
  }

  switch (typ) {
    case "const":
      return;
    case "and":
    case "or": {
      const children = Array.isArray(expr.children) ? expr.children : [];
      if (children.length === 0) {
        ctx.issues.push(issue(ctx.path, `${typ} 条件至少需要一个子条件`));
      }
      children.forEach((child, index) =>
        validateExprRefs(child, { ...ctx, path: `${ctx.path}.children[${index}]` })
      );
      return;
    }
    case "not":
      validateExprRefs(expr.child, { ...ctx, path: `${ctx.path}.child` });
      return;
    case "pixel_point":
    case "cast_bar_changed": {
      const pointId = stringField(expr.point_id);
      if (!pointId) {
        ctx.issues.push(issue(ctx.path, "点位条件缺少 point_id"));
      } else if (!ctx.pointIds.has(pointId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的点位：${pointId}`));
      }
      return;
    }
    case "pixel_skill":
    case "skill_metric_ge": {
      const skillId = stringField(expr.skill_id);
      if (!skillId) {
        ctx.issues.push(issue(ctx.path, "技能条件缺少 skill_id"));
      } else if (!ctx.skillIds.has(skillId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的技能：${skillId}`));
      }
      return;
    }
    default:
      ctx.issues.push(issue(ctx.path, `未知条件类型：${typ}`));
  }
}

export function validateProfileForSave(profile: Profile): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = validateBaseConfig(profile);
  const skillIds = new Set<string>();
  const pointIds = new Set<string>();
  const pickHotkey = normalizeHotkey(profile.base.pick.confirm_hotkey);
  const toggleHotkey = normalizeHotkey(profile.base.exec.toggle_hotkey);

  if (pickHotkey && toggleHotkey && pickHotkey === toggleHotkey) {
    issues.push(issue("base.exec.toggle_hotkey", `取色确认热键和引擎启停热键不能相同：${toggleHotkey}`));
  }

  for (const skill of profile.skills.skills) {
    const skillId = skill.id.trim();
    if (!skillId) {
      issues.push(issue("skills", "技能 ID 不能为空"));
    } else if (skillIds.has(skillId)) {
      issues.push(issue(`skills.${skillId}`, `技能 ID 重复：${skillId}`));
    } else {
      skillIds.add(skillId);
    }

    if (!skill.name.trim()) {
      issues.push(issue(`skills.${skillId || "unknown"}.name`, "技能名称不能为空"));
    }
    issues.push(...validatePixelSpec(skill.pixel, `skills.${skillId || "unknown"}.pixel`));

    const ammoCharges = new Set<number>();
    skill.ammo_stages.forEach((stage, index) => {
      if (ammoCharges.has(stage.charges_left)) {
        issues.push(
          issue(
            `skills.${skillId || "unknown"}.ammo_stages[${index}].charges_left`,
            `弹药阶段剩余层数重复：${stage.charges_left}`
          )
        );
      } else {
        ammoCharges.add(stage.charges_left);
      }
      issues.push(
        ...validatePixelSpec(
          stage.pixel,
          `skills.${skillId || "unknown"}.ammo_stages[${index}].pixel`
        )
      );
    });
  }

  for (const [pointIndex, point] of profile.points.points.entries()) {
    const pointId = point.id.trim();
    if (!pointId) {
      issues.push(issue("points", "点位 ID 不能为空"));
    } else if (pointIds.has(pointId)) {
      issues.push(issue(`points.${pointId}`, `点位 ID 重复：${pointId}`));
    } else {
      pointIds.add(pointId);
    }
    issues.push(...validatePointConfig(point, `points.${pointId || pointIndex}`));
  }

  const castBarPointId = profile.base.cast_bar.point_id.trim();
  if (profile.base.cast_bar.mode !== "timer") {
    if (!castBarPointId) {
      issues.push(issue("base.cast_bar.point_id", "非计时模式需要配置读条点位"));
    } else if (!pointIds.has(castBarPointId)) {
      issues.push(issue("base.cast_bar.point_id", `读条点位不存在：${castBarPointId}`));
    }
  } else if (castBarPointId && !pointIds.has(castBarPointId)) {
    issues.push(issue("base.cast_bar.point_id", `读条点位不存在：${castBarPointId}`));
  }

  profile.rotations.forEach((rotation, rotationIndex) => {
    if (!isIntegerInRange(rotation.poll_interval_ms, 1, 10000)) {
      issues.push(
        issue(`rotations[${rotationIndex}].poll_interval_ms`, "循环轮询间隔必须在 1-10000ms 之间")
      );
    }
    rotation.phases.forEach((phase, phaseIndex) => {
      phase.skills.forEach((slot, slotIndex) => {
        const slotPath = `rotations[${rotationIndex}].phases[${phaseIndex}].skills[${slotIndex}]`;
        const skillId = slot.skill_id.trim();
        if (skillId && !skillIds.has(skillId)) {
          issues.push(issue(`${slotPath}.skill_id`, `技能槽引用了不存在的技能：${skillId}`));
        }
        validateExprRefs(slot.condition_expr, {
          skillIds,
          pointIds,
          issues,
          path: `${slotPath}.condition_expr`,
        });
        validateExprRefs(slot.start_expr, {
          skillIds,
          pointIds,
          issues,
          path: `${slotPath}.start_expr`,
        });
        validateExprRefs(slot.complete_expr, {
          skillIds,
          pointIds,
          issues,
          path: `${slotPath}.complete_expr`,
        });
      });
    });
  });

  return issues;
}

export function validateProfileForRun(profile: Profile): ProfileValidationIssue[] {
  const issues = validateProfileForSave(profile);
  const firstRotation = profile.rotations[0];

  if (!firstRotation) {
    issues.push(issue("rotations", "请先创建并保存一个循环"));
    return issues;
  }

  if (firstRotation.phases.length === 0) {
    issues.push(issue("rotations[0].phases", "循环至少需要一个阶段"));
    return issues;
  }

  let executableSlots = 0;
  const skillById = new Map(profile.skills.skills.map((skill) => [skill.id.trim(), skill]));

  firstRotation.phases.forEach((phase, phaseIndex) => {
    if (phase.skills.length === 0) {
      issues.push(issue(`rotations[0].phases[${phaseIndex}].skills`, "阶段没有技能槽"));
      return;
    }

    phase.skills.forEach((slot, slotIndex) => {
      const path = `rotations[0].phases[${phaseIndex}].skills[${slotIndex}]`;
      const skillId = slot.skill_id.trim();
      if (!skillId) {
        issues.push(issue(`${path}.skill_id`, "技能槽未选择技能"));
        return;
      }

      const skill = skillById.get(skillId);
      if (!skill) return;
      if (!skill.enabled) return;

      executableSlots += 1;
      if (!skill.trigger_key.trim()) {
        issues.push(issue(`skills.${skillId}.trigger_key`, `启用技能缺少触发键：${skill.name || skillId}`));
      }
    });
  });

  if (executableSlots === 0) {
    issues.push(issue("rotations[0]", "循环中没有可执行的启用技能"));
  }

  return issues;
}

export function validateProfileForEngineStart(profile: Profile): ProfileValidationIssue[] {
  const issues = validateProfileForRun(profile);
  if (!profile.base.exec.enabled) {
    issues.push(issue("base.exec.enabled", "请先在基础配置中启用宏执行"));
  }
  return issues;
}

export function formatProfileIssue(issue: ProfileValidationIssue): string {
  return `${issue.message}（${issue.path}）`;
}

export function firstProfileError(issues: ProfileValidationIssue[]): string | null {
  const first = issues.find((item) => item.severity === "error");
  return first ? formatProfileIssue(first) : null;
}
