export interface SimulationDebugEvent {
  event: string;
  outcome: string;
  reason: string;
  timeMs: number;
  skillId: string;
}

export interface SimulationSummary {
  total: number;
  executed: number;
  skipped: number;
  transitions: number;
  runtimeActions: number;
  success: number;
  notReady: number;
  failed: number;
  durationMs: number;
  uniqueSkills: number;
  topReasons: Array<{ reason: string; count: number }>;
}

export function summarizeSimulation(events: SimulationDebugEvent[]): SimulationSummary {
  const reasonCounts = new Map<string, number>();
  const skillIds = new Set<string>();

  let executed = 0;
  let skipped = 0;
  let transitions = 0;
  let runtimeActions = 0;
  let success = 0;
  let notReady = 0;
  let failed = 0;
  let durationMs = 0;

  for (const event of events) {
    if (event.event === "skip" || event.event === "assist_skip") skipped += 1;
    else if (event.event === "phase_transition") transitions += 1;
    else if (event.event === "runtime_action") runtimeActions += 1;
    else executed += 1;

    if (event.outcome === "Success") success += 1;
    else if (event.outcome === "NOT_READY") notReady += 1;
    else if (event.outcome === "Failed") failed += 1;

    if (event.reason) {
      reasonCounts.set(event.reason, (reasonCounts.get(event.reason) || 0) + 1);
    }
    if (event.skillId) skillIds.add(event.skillId);
    durationMs = Math.max(durationMs, event.timeMs);
  }

  const topReasons = [...reasonCounts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason))
    .slice(0, 5);

  return {
    total: events.length,
    executed,
    skipped,
    transitions,
    runtimeActions,
    success,
    notReady,
    failed,
    durationMs,
    uniqueSkills: skillIds.size,
    topReasons,
  };
}

export function simulationDebugJson(events: SimulationDebugEvent[]): string {
  return JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      summary: summarizeSimulation(events),
      events,
    },
    null,
    2
  );
}

export function simulationEventLabel(event: string): string {
  const labels: Record<string, string> = {
    execute: "执行",
    assist_execute: "辅助执行",
    attempt: "尝试",
    skip: "跳过",
    assist_skip: "辅助跳过",
    runtime_action: "状态动作",
    phase_transition: "阶段跳转",
  };
  return labels[event] ?? event;
}

export function simulationOutcomeTagType(outcome: string): "success" | "warning" | "error" | "info" | "default" {
  if (outcome === "Success") return "success";
  if (outcome === "Failed") return "error";
  if (outcome === "NOT_READY") return "warning";
  if (outcome === "Applied") return "info";
  return "default";
}

export function simulationOutcomeLabel(outcome: string): string {
  const labels: Record<string, string> = {
    Success: "成功",
    Failed: "失败",
    NOT_READY: "未就绪",
    Applied: "已应用",
  };
  return labels[outcome] ?? outcome;
}

export function simulationReasonLabel(reason: string): string {
  if (!reason) return "";
  if (reason.startsWith("cooldown_until=")) return `冷却中（${reason}）`;
  if (reason.startsWith("shots_per_cycle_exhausted=")) return `本轮次数已用完（${reason}）`;
  if (reason.startsWith("condition_false:")) return `条件不满足（${reason}）`;
  if (reason.startsWith("condition_unknown:")) return `条件未知（${reason}）`;
  if (reason.startsWith("rule:")) return `命中跳转规则（${reason}）`;
  if (reason.startsWith("fallback:stay")) return "Fallback：停留当前阶段";
  if (reason.startsWith("fallback:next")) return "Fallback：进入下一阶段";
  if (reason.startsWith("fallback:phase->")) return `Fallback：跳转到 ${reason.replace("fallback:phase->", "")}`;
  if (reason.startsWith("runtime_action:")) return `运行状态动作（${reason}）`;

  const labels: Record<string, string> = {
    no_condition: "无条件",
    condition_true: "条件满足",
    skill_id_empty: "技能 ID 为空",
    skill_missing: "技能不存在",
    skill_disabled: "技能已禁用",
    ammo_unavailable: "弹药不可用",
    success: "成功",
    hybrid_assume_no_expr: "无完成信号，按读条成功",
    hybrid_assume_timeout: "完成信号超时，按策略成功",
    complete_signal_missing: "完成信号缺失",
    timeout: "超时",
    no_cast_start: "未检测到释放开始",
    send_key_failed: "发键失败",
    send_key_failed_retry: "重试发键失败",
  };
  return labels[reason] ? `${labels[reason]}（${reason}）` : reason;
}
