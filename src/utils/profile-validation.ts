import type { Profile } from "../types/profile";
import type { Point } from "../types/point";
import type { PixelSpec, SampleConfig } from "../types/skill";
import type { AttemptPolicy, ObserverActionSlot, RuntimeAction, SkillSlot } from "../types/cycle";

export interface ProfileValidationIssue {
  path: string;
  message: string;
  severity: "error" | "warning";
}

interface ExprRefContext {
  skillIds: Set<string>;
  pointIds: Set<string>;
  markerValues: Map<string, Set<string>>;
  timerIds: Set<string>;
  counterIds: Set<string>;
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
  if (castBarMode !== "timer" && castBarMode !== "pixel" && castBarMode !== "roi") {
    issues.push(issue("base.cast_bar.mode", "读条模式必须是 timer、pixel 或 roi"));
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
  const roi = base.cast_bar.roi;
  if (!roi) {
    issues.push(issue("base.cast_bar.roi", "施法条 ROI 配置缺失"));
  } else {
    if ((roi.enabled || castBarMode === "roi") && !roi.monitor.trim()) {
      issues.push(issue("base.cast_bar.roi.monitor", "施法条 ROI 必须指定显示器"));
    }
    if ((roi.enabled || castBarMode === "roi") && !isIntegerInRange(roi.width, 1, 2000)) {
      issues.push(issue("base.cast_bar.roi.width", "施法条 ROI 宽度必须在 1-2000 之间"));
    }
    if ((roi.enabled || castBarMode === "roi") && !isIntegerInRange(roi.height, 1, 500)) {
      issues.push(issue("base.cast_bar.roi.height", "施法条 ROI 高度必须在 1-500 之间"));
    }
    if (!isByte(roi.diff_threshold)) {
      issues.push(issue("base.cast_bar.roi.diff_threshold", "施法条 ROI 帧差阈值必须在 0-255 之间"));
    }
    if (!Number.isFinite(roi.min_changed_ratio) || roi.min_changed_ratio < 0 || roi.min_changed_ratio > 1) {
      issues.push(issue("base.cast_bar.roi.min_changed_ratio", "施法条 ROI 变化比例必须在 0-1 之间"));
    }
    if (!isByte(roi.border_tolerance)) {
      issues.push(issue("base.cast_bar.roi.border_tolerance", "施法条 ROI 边框容差必须在 0-255 之间"));
    }
    if (
      !Number.isFinite(roi.min_border_match_ratio) ||
      roi.min_border_match_ratio < 0 ||
      roi.min_border_match_ratio > 1
    ) {
      issues.push(issue("base.cast_bar.roi.min_border_match_ratio", "施法条 ROI 边框命中比例必须在 0-1 之间"));
    }
    if (!isIntegerInRange(roi.confirm_frames, 1, 10)) {
      issues.push(issue("base.cast_bar.roi.confirm_frames", "施法条 ROI 确认帧数必须在 1-10 之间"));
    }
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

  const pickHotkey = normalizeHotkey(base.pick.confirm_hotkey);
  const toggleHotkey = normalizeHotkey(base.exec.toggle_hotkey);
  if (pickHotkey && toggleHotkey && pickHotkey === toggleHotkey) {
    issues.push(issue("base.exec.toggle_hotkey", `取色确认热键和引擎启停热键不能相同：${toggleHotkey}`));
  }

  return issues;
}

function validateAttemptPolicy(
  policy: AttemptPolicy | null | undefined,
  path: string
): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  if (!policy) return issues;

  if (!isIntegerInRange(policy.max_attempts, 1, 21)) {
    issues.push(issue(`${path}.max_attempts`, "总尝试次数必须在 1-21 之间"));
  }
  if (!isIntegerInRange(policy.start_timeout_ms, 1, 600000)) {
    issues.push(issue(`${path}.start_timeout_ms`, "释放开始超时必须在 1-600000ms 之间"));
  }
  if (!isIntegerInRange(policy.complete_timeout_ms, 0, 600000)) {
    issues.push(issue(`${path}.complete_timeout_ms`, "释放完成超时必须在 0-600000ms 之间"));
  }
  if (!isIntegerInRange(policy.retry_delay_ms, 0, 60000)) {
    issues.push(issue(`${path}.retry_delay_ms`, "重试间隔必须在 0-60000ms 之间"));
  }
  if (!["hold_phase", "next_slot", "next_phase"].includes(policy.failure_policy)) {
    issues.push(issue(`${path}.failure_policy`, "失败策略必须是 hold_phase、next_slot 或 next_phase"));
  }
  if (!["fail", "assume_success_after_timeout"].includes(policy.complete_fallback)) {
    issues.push(issue(`${path}.complete_fallback`, "完成超时兜底策略无效"));
  }

  return issues;
}

function markerValueAllowed(
  markerValues: Map<string, Set<string>>,
  markerId: string,
  value: string
): boolean {
  const allowed = markerValues.get(markerId);
  return !!allowed && (allowed.size === 0 || allowed.has(value.trim()));
}

function validateRuntimeActions(
  actions: RuntimeAction[] | null | undefined,
  markerValues: Map<string, Set<string>>,
  timerIds: Set<string>,
  counterIds: Set<string>,
  path: string
): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  (actions ?? []).forEach((action, index) => {
    switch (action.type) {
      case "set_marker": {
        const markerId = stringField(action.marker_id);
        if (!markerId) {
          issues.push(issue(`${path}[${index}].marker_id`, "标记动作缺少 marker_id"));
        } else if (!markerValues.has(markerId)) {
          issues.push(issue(`${path}[${index}].marker_id`, `引用了不存在的标记：${markerId}`));
        } else if (!markerValueAllowed(markerValues, markerId, action.value)) {
          issues.push(issue(`${path}[${index}].value`, `标记值不在允许范围内：${action.value}`));
        }
        return;
      }
      case "clear_marker": {
        const markerId = stringField(action.marker_id);
        if (!markerId) {
          issues.push(issue(`${path}[${index}].marker_id`, "清除标记动作缺少 marker_id"));
        } else if (!markerValues.has(markerId)) {
          issues.push(issue(`${path}[${index}].marker_id`, `引用了不存在的标记：${markerId}`));
        }
        return;
      }
      case "record_timer":
      case "reset_timer": {
        const timerId = stringField(action.timer_id);
        if (!timerId) {
          issues.push(issue(`${path}[${index}].timer_id`, "时间动作缺少 timer_id"));
        } else if (!timerIds.has(timerId)) {
          issues.push(issue(`${path}[${index}].timer_id`, `引用了不存在的时间标记：${timerId}`));
        }
        return;
      }
      case "increment_counter":
      case "set_counter":
      case "reset_counter": {
        const counterId = stringField(action.counter_id);
        if (!counterId) {
          issues.push(issue(`${path}[${index}].counter_id`, "计数器动作缺少 counter_id"));
        } else if (!counterIds.has(counterId)) {
          issues.push(issue(`${path}[${index}].counter_id`, `引用了不存在的计数器：${counterId}`));
        }
        return;
      }
    }
  });
  return issues;
}

function validateSkillSlotRefs(
  slot: SkillSlot,
  path: string,
  ctx: Omit<ExprRefContext, "path">
): void {
  const skillId = slot.skill_id.trim();
  if (skillId && !ctx.skillIds.has(skillId)) {
    ctx.issues.push(issue(`${path}.skill_id`, `技能槽引用了不存在的技能：${skillId}`));
  }
  if (
    slot.slot_role !== undefined &&
    !["mandatory", "priority", "filler"].includes(slot.slot_role)
  ) {
    ctx.issues.push(issue(`${path}.slot_role`, "skill slot role must be mandatory, priority, or filler"));
  }
  if (slot.protected_release !== undefined && typeof slot.protected_release !== "boolean") {
    ctx.issues.push(issue(`${path}.protected_release`, "保护释放必须是布尔值"));
  }
  if (
    slot.readiness_policy !== undefined &&
    !["required", "advisory"].includes(slot.readiness_policy)
  ) {
    ctx.issues.push(issue(`${path}.readiness_policy`, "readiness policy must be required or advisory"));
  }
  validateExprRefs(slot.condition_expr, { ...ctx, path: `${path}.condition_expr` });
  validateExprRefs(slot.readiness_expr ?? null, { ...ctx, path: `${path}.readiness_expr` });
  validateExprRefs(slot.start_expr, { ...ctx, path: `${path}.start_expr` });
  validateExprRefs(slot.complete_expr, { ...ctx, path: `${path}.complete_expr` });
  ctx.issues.push(...validateAttemptPolicy(slot.attempt_policy, `${path}.attempt_policy`));
  ctx.issues.push(
    ...validateRuntimeActions(
      slot.post_actions,
      ctx.markerValues,
      ctx.timerIds,
      ctx.counterIds,
      `${path}.post_actions`
    )
  );
}

function validateObserverActionSlot(
  slot: ObserverActionSlot,
  path: string,
  ctx: Omit<ExprRefContext, "path">
): void {
  const slotId = stringField(slot.id);
  if (!slotId) {
    ctx.issues.push(issue(`${path}.id`, "观察动作 ID 不能为空"));
  }
  if (!stringField(slot.label)) {
    ctx.issues.push(issue(`${path}.label`, "观察动作名称不能为空"));
  }
  validateExprRefs(slot.condition_expr, { ...ctx, path: `${path}.condition_expr` });
  if ((slot.actions ?? []).length === 0) {
    ctx.issues.push(issue(`${path}.actions`, "观察动作至少需要一个运行状态动作"));
  }
  ctx.issues.push(
    ...validateRuntimeActions(
      slot.actions,
      ctx.markerValues,
      ctx.timerIds,
      ctx.counterIds,
      `${path}.actions`
    )
  );
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
    case "pixel_point_not_match":
    case "pixel_point_black":
    case "pixel_point_not_black":
    case "cast_bar_changed": {
      const pointId = stringField(expr.point_id);
      if (!pointId) {
        ctx.issues.push(issue(ctx.path, "点位条件缺少 point_id"));
      } else if (!ctx.pointIds.has(pointId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的点位：${pointId}`));
      }
      return;
    }
    case "pixel_point_nearest": {
      const expectedPointId = stringField(expr.expected_point_id);
      if (!expectedPointId) {
        ctx.issues.push(issue(ctx.path, "最近点位条件缺少 expected_point_id"));
      } else if (!ctx.pointIds.has(expectedPointId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的点位：${expectedPointId}`));
      }
      const candidatePointIds = Array.isArray(expr.candidate_point_ids)
        ? expr.candidate_point_ids.map(stringField)
        : [];
      if (candidatePointIds.length < 2) {
        ctx.issues.push(issue(ctx.path, "最近点位条件至少需要 2 个候选点位"));
      }
      if (expectedPointId && !candidatePointIds.includes(expectedPointId)) {
        ctx.issues.push(issue(ctx.path, "候选点位必须包含 expected_point_id"));
      }
      candidatePointIds.forEach((pointId) => {
        if (!pointId) {
          ctx.issues.push(issue(ctx.path, "候选点位 ID 不能为空"));
        } else if (!ctx.pointIds.has(pointId)) {
          ctx.issues.push(issue(ctx.path, `引用了不存在的点位：${pointId}`));
        }
      });
      return;
    }
    case "cast_bar_roi_changed":
    case "cast_bar_roi_border_visible":
    case "cast_bar_roi_gone":
      return;
    case "pixel_skill":
    case "pixel_skill_not_match":
    case "pixel_skill_black":
    case "pixel_skill_not_black":
    case "skill_metric_ge": {
      const skillId = stringField(expr.skill_id);
      if (!skillId) {
        ctx.issues.push(issue(ctx.path, "技能条件缺少 skill_id"));
      } else if (!ctx.skillIds.has(skillId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的技能：${skillId}`));
      }
      return;
    }
    case "timer_elapsed_ge":
    case "timer_elapsed_lt": {
      const timerId = stringField(expr.timer_id);
      if (!timerId) {
        ctx.issues.push(issue(ctx.path, "时间条件缺少 timer_id"));
      } else if (!ctx.timerIds.has(timerId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的时间标记：${timerId}`));
      }
      return;
    }
    case "marker_eq":
    case "marker_ne": {
      const markerId = stringField(expr.marker_id);
      const markerValue = stringField(expr.value);
      if (!markerId) {
        ctx.issues.push(issue(ctx.path, "标记条件缺少 marker_id"));
      } else if (!ctx.markerValues.has(markerId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的标记：${markerId}`));
      } else if (!markerValueAllowed(ctx.markerValues, markerId, markerValue)) {
        ctx.issues.push(issue(ctx.path, `标记值不在允许范围内：${markerValue}`));
      }
      return;
    }
    case "counter_ge":
    case "counter_eq":
    case "counter_gt": {
      const counterId = stringField(expr.counter_id);
      if (!counterId) {
        ctx.issues.push(issue(ctx.path, "计数器条件缺少 counter_id"));
      } else if (!ctx.counterIds.has(counterId)) {
        ctx.issues.push(issue(ctx.path, `引用了不存在的计数器：${counterId}`));
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
  if (profile.base.cast_bar.mode === "pixel") {
    if (!castBarPointId) {
      issues.push(issue("base.cast_bar.point_id", "像素读条模式需要配置读条点位"));
    } else if (!pointIds.has(castBarPointId)) {
      issues.push(issue("base.cast_bar.point_id", `读条点位不存在：${castBarPointId}`));
    }
  } else if (castBarPointId && !pointIds.has(castBarPointId)) {
    issues.push(issue("base.cast_bar.point_id", `读条点位不存在：${castBarPointId}`));
  }

  profile.rotations.forEach((rotation, rotationIndex) => {
    const markerValues = new Map<string, Set<string>>();
    const timerIds = new Set<string>();
    const counterIds = new Set<string>();
    const phaseNames = new Set<string>();

    (rotation.state_schema?.markers ?? []).forEach((marker, markerIndex) => {
      const markerId = marker.id.trim();
      const markerPath = `rotations[${rotationIndex}].state_schema.markers[${markerIndex}]`;
      if (!markerId) {
        issues.push(issue(`${markerPath}.id`, "标记 ID 不能为空"));
      } else if (markerValues.has(markerId)) {
        issues.push(issue(`${markerPath}.id`, `标记 ID 重复：${markerId}`));
      }
      if (!marker.name.trim()) {
        issues.push(issue(`${markerPath}.name`, "标记名称不能为空"));
      }
      if (!marker.initial_value.trim()) {
        issues.push(issue(`${markerPath}.initial_value`, "标记初始值不能为空"));
      }
      const allowed = new Set<string>();
      (marker.allowed_values ?? []).forEach((value, valueIndex) => {
        const normalized = value.trim();
        if (!normalized) {
          issues.push(issue(`${markerPath}.allowed_values[${valueIndex}]`, "标记允许值不能为空"));
        } else if (allowed.has(normalized)) {
          issues.push(issue(`${markerPath}.allowed_values[${valueIndex}]`, `标记允许值重复：${normalized}`));
        } else {
          allowed.add(normalized);
        }
      });
      if (allowed.size > 0 && !allowed.has(marker.initial_value.trim())) {
        issues.push(issue(`${markerPath}.initial_value`, `标记初始值不在允许范围内：${marker.initial_value}`));
      }
      if (markerId && !markerValues.has(markerId)) {
        markerValues.set(markerId, allowed);
      }
    });

    (rotation.state_schema?.timers ?? []).forEach((timer, timerIndex) => {
      const timerId = timer.id.trim();
      const timerPath = `rotations[${rotationIndex}].state_schema.timers[${timerIndex}]`;
      if (!timerId) {
        issues.push(issue(`${timerPath}.id`, "时间标记 ID 不能为空"));
      } else if (timerIds.has(timerId)) {
        issues.push(issue(`${timerPath}.id`, `时间标记 ID 重复：${timerId}`));
      } else {
        timerIds.add(timerId);
      }
      if (!timer.name.trim()) {
        issues.push(issue(`${timerPath}.name`, "时间标记名称不能为空"));
      }
    });

    (rotation.state_schema?.counters ?? []).forEach((counter, counterIndex) => {
      const counterId = counter.id.trim();
      const counterPath = `rotations[${rotationIndex}].state_schema.counters[${counterIndex}]`;
      if (!counterId) {
        issues.push(issue(`${counterPath}.id`, "计数器 ID 不能为空"));
      } else if (counterIds.has(counterId)) {
        issues.push(issue(`${counterPath}.id`, `计数器 ID 重复：${counterId}`));
      } else {
        counterIds.add(counterId);
      }
      if (!counter.name.trim()) {
        issues.push(issue(`${counterPath}.name`, "计数器名称不能为空"));
      }
      if (!Number.isInteger(counter.initial_value)) {
        issues.push(issue(`${counterPath}.initial_value`, "计数器初始值必须是整数"));
      }
    });

    if (!isIntegerInRange(rotation.poll_interval_ms, 1, 10000)) {
      issues.push(issue(`rotations[${rotationIndex}].poll_interval_ms`, "循环轮询间隔必须在 1-10000ms 之间"));
    }

    rotation.phases.forEach((phase, phaseIndex) => {
      const phaseName = phase.name.trim();
      if (!phaseName) return;
      if (phaseNames.has(phaseName)) {
        issues.push(issue(`rotations[${rotationIndex}].phases[${phaseIndex}].name`, `阶段名称重复：${phaseName}`));
      } else {
        phaseNames.add(phaseName);
      }
    });

    rotation.phases.forEach((phase, phaseIndex) => {
      const phasePath = `rotations[${rotationIndex}].phases[${phaseIndex}]`;
      issues.push(
        ...validateRuntimeActions(
          phase.entry_actions,
          markerValues,
          timerIds,
          counterIds,
          `${phasePath}.entry_actions`
        )
      );
      (phase.transition_rules ?? []).forEach((rule, ruleIndex) => {
        const rulePath = `${phasePath}.transition_rules[${ruleIndex}]`;
        const targetPhase = rule.target_phase.trim();
        if (!targetPhase) {
          issues.push(issue(`${rulePath}.target_phase`, "目标阶段不能为空"));
        } else if (!phaseNames.has(targetPhase)) {
          issues.push(issue(`${rulePath}.target_phase`, `引用了不存在的阶段：${targetPhase}`));
        }
        if (!rule.condition_expr) {
          issues.push(issue(`${rulePath}.condition_expr`, "跳转条件不能为空"));
        }
        const exprCtx = {
          skillIds,
          pointIds,
          markerValues,
          timerIds,
          counterIds,
          issues,
        };
        validateExprRefs(rule.condition_expr, { ...exprCtx, path: `${rulePath}.condition_expr` });
      });
      if (phase.fallback_transition?.type === "phase") {
        const targetPhase = phase.fallback_transition.target_phase.trim();
        if (!targetPhase) {
          issues.push(issue(`${phasePath}.fallback_transition.target_phase`, "Fallback 目标阶段不能为空"));
        } else if (!phaseNames.has(targetPhase)) {
          issues.push(issue(`${phasePath}.fallback_transition.target_phase`, `Fallback 引用了不存在的阶段：${targetPhase}`));
        }
      }
      const exprCtx = {
        skillIds,
        pointIds,
        markerValues,
        timerIds,
        counterIds,
        issues,
      };
      phase.skills.forEach((slot, slotIndex) => {
        validateSkillSlotRefs(slot, `${phasePath}.skills[${slotIndex}]`, exprCtx);
      });
    });

    const assistLaneIds = new Set<string>();
    (rotation.assist_lanes ?? []).forEach((lane, laneIndex) => {
      const lanePath = `rotations[${rotationIndex}].assist_lanes[${laneIndex}]`;
      const laneId = lane.id.trim();
      if (!laneId) {
        issues.push(issue(`${lanePath}.id`, "辅助 lane ID 不能为空"));
      } else if (assistLaneIds.has(laneId)) {
        issues.push(issue(`${lanePath}.id`, `辅助 lane ID 重复：${laneId}`));
      } else {
        assistLaneIds.add(laneId);
      }
      if (!lane.name.trim()) {
        issues.push(issue(`${lanePath}.name`, "辅助 lane 名称不能为空"));
      }
      if (!isIntegerInRange(lane.check_interval_ms, 10, 600000)) {
        issues.push(issue(`${lanePath}.check_interval_ms`, "辅助 lane 检查间隔必须在 10-600000ms 之间"));
      }
      if (!["idle_only", "complete_wait", "any_wait"].includes(lane.interrupt_policy)) {
        issues.push(issue(`${lanePath}.interrupt_policy`, "辅助 lane 打断策略无效"));
      }
      const exprCtx = {
        skillIds,
        pointIds,
        markerValues,
        timerIds,
        counterIds,
        issues,
      };
      lane.skills.forEach((slot, slotIndex) => {
        validateSkillSlotRefs(slot, `${lanePath}.skills[${slotIndex}]`, exprCtx);
      });
    });

    const observerLaneIds = new Set<string>();
    (rotation.observer_lanes ?? []).forEach((lane, laneIndex) => {
      const lanePath = `rotations[${rotationIndex}].observer_lanes[${laneIndex}]`;
      const laneId = lane.id.trim();
      if (!laneId) {
        issues.push(issue(`${lanePath}.id`, "观察 lane ID 不能为空"));
      } else if (observerLaneIds.has(laneId)) {
        issues.push(issue(`${lanePath}.id`, `观察 lane ID 重复：${laneId}`));
      } else {
        observerLaneIds.add(laneId);
      }
      if (!lane.name.trim()) {
        issues.push(issue(`${lanePath}.name`, "观察 lane 名称不能为空"));
      }
      if (!isIntegerInRange(lane.check_interval_ms, 10, 600000)) {
        issues.push(issue(`${lanePath}.check_interval_ms`, "观察 lane 检查间隔必须在 10-600000ms 之间"));
      }
      const exprCtx = {
        skillIds,
        pointIds,
        markerValues,
        timerIds,
        counterIds,
        issues,
      };
      (lane.actions ?? []).forEach((slot, slotIndex) => {
        validateObserverActionSlot(slot, `${lanePath}.actions[${slotIndex}]`, exprCtx);
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
      if (!skill.trigger_key.trim()) {
        issues.push(issue(`${path}.trigger_key`, `启用技能缺少触发键：${skillId}`));
        return;
      }
      executableSlots += 1;
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

export function firstProfileError(issues: ProfileValidationIssue[]): string | null {
  return issues.find((item) => item.severity === "error")?.message ?? null;
}
