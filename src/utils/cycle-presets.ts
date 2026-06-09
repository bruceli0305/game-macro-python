import type { Expr } from "../types/ast";
import type { AttemptPolicy, CycleConfig, RuntimeAction, SkillSlot } from "../types/cycle";

export type CyclePresetId = "power_virtuoso_greatsword" | "condi_quickness_firebrand";

export interface CyclePresetOption {
  label: string;
  value: CyclePresetId;
  description: string;
}

interface CyclePresetDefinition extends CyclePresetOption {
  rotation: CycleConfig;
}

const defaultAttemptPolicy: AttemptPolicy = {
  max_attempts: 1,
  start_timeout_ms: 700,
  complete_timeout_ms: 2400,
  retry_delay_ms: 80,
  failure_policy: "next_slot",
  complete_fallback: "assume_success_after_timeout",
};

const burstAttemptPolicy: AttemptPolicy = {
  max_attempts: 1,
  start_timeout_ms: 900,
  complete_timeout_ms: 3200,
  retry_delay_ms: 100,
  failure_policy: "hold_phase",
  complete_fallback: "assume_success_after_timeout",
};

function constExpr(value: boolean): Expr {
  return { type: "const", value };
}

function markerEq(markerId: string, value: string): Expr {
  return { type: "marker_eq", marker_id: markerId, value };
}

function counterGe(counterId: string, value: number): Expr {
  return { type: "counter_ge", counter_id: counterId, value };
}

function timerElapsedGe(timerId: string, ms: number): Expr {
  return { type: "timer_elapsed_ge", timer_id: timerId, ms };
}

function recordTimer(timerId: string): RuntimeAction {
  return { type: "record_timer", timer_id: timerId };
}

function setMarker(markerId: string, value: string): RuntimeAction {
  return { type: "set_marker", marker_id: markerId, value };
}

function incrementCounter(counterId: string, by = 1): RuntimeAction {
  return { type: "increment_counter", counter_id: counterId, by };
}

function slot(
  skillId: string,
  label: string,
  priority: number,
  options: {
    condition?: Expr;
    attemptPolicy?: AttemptPolicy;
    protectedRelease?: boolean;
    overrideCastMs?: number;
    postActions?: RuntimeAction[];
  } = {},
): SkillSlot {
  return {
    skill_id: skillId,
    priority,
    label,
    condition_expr: options.condition ?? null,
    start_expr: constExpr(true),
    complete_expr: { type: "pixel_skill_black", skill_id: skillId, tolerance: 24 },
    override_cast_ms: options.overrideCastMs ?? null,
    protected_release: options.protectedRelease ?? false,
    attempt_policy: options.attemptPolicy ?? defaultAttemptPolicy,
    post_actions: options.postActions ?? [],
  };
}

const presets: Record<CyclePresetId, CyclePresetDefinition> = {
  power_virtuoso_greatsword: {
    label: "直伤大剑灵刃",
    value: "power_virtuoso_greatsword",
    description: "按入口判定、副武器起手、主武器循环、副武器循环和切武器爆发拆分。",
    rotation: {
      name: "直伤大剑灵刃 - 状态机模板",
      poll_interval_ms: 80,
      max_cycles: 0,
      state_schema: {
        markers: [
          {
            id: "weapon",
            name: "当前武器组",
            initial_value: "unknown",
            allowed_values: ["unknown", "main", "alt"],
          },
        ],
        timers: [
          { id: "last_main_burst", name: "主武器爆发时间", reset_on_cycle_start: true },
          { id: "last_entry_swap", name: "入口切武器时间", reset_on_cycle_start: true },
        ],
        counters: [
          {
            id: "main_wp4_count",
            name: "主武器 4 计数",
            initial_value: 0,
            reset_on_phase_entry: true,
            reset_on_cycle_start: true,
          },
          {
            id: "main_wp2_count",
            name: "主武器 2 计数",
            initial_value: 0,
            reset_on_phase_entry: true,
            reset_on_cycle_start: true,
          },
          {
            id: "alt_twp5_count",
            name: "副武器 5 计数",
            initial_value: 0,
            reset_on_phase_entry: true,
            reset_on_cycle_start: true,
          },
          {
            id: "alt_twp3_count",
            name: "副武器 3 计数",
            initial_value: 0,
            reset_on_phase_entry: true,
            reset_on_cycle_start: true,
          },
        ],
      },
      phases: [
        {
          name: "入口判定",
          complete_when: "any_fired",
          entry_actions: [],
          transition_rules: [
            { label: "已在主武器", condition_expr: markerEq("weapon", "main"), target_phase: "主武器循环" },
            { label: "已在副武器", condition_expr: markerEq("weapon", "alt"), target_phase: "副武器起手" },
          ],
          fallback_transition: { type: "next" },
          skills: [
            slot("virt_weapon_swap", "入口切武器/校正武器组", 1, {
              protectedRelease: true,
              postActions: [setMarker("weapon", "alt"), recordTimer("last_entry_swap")],
            }),
          ],
        },
        {
          name: "副武器起手",
          complete_when: "none_ready",
          entry_actions: [setMarker("weapon", "alt")],
          transition_rules: [
            {
              label: "副武器起手完成",
              condition_expr: counterGe("alt_twp5_count", 1),
              target_phase: "主武器循环",
            },
          ],
          fallback_transition: { type: "next" },
          skills: [
            slot("virt_focus5", "副武器 5：关键爆发", 1, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
              postActions: [incrementCounter("alt_twp5_count")],
            }),
            slot("virt_focus4", "副武器 4：补伤害/触发", 2, {
              protectedRelease: true,
              postActions: [incrementCounter("alt_twp3_count")],
            }),
          ],
        },
        {
          name: "主武器循环",
          complete_when: "none_ready",
          entry_actions: [setMarker("weapon", "main")],
          transition_rules: [
            {
              label: "主武器爆发窗口",
              condition_expr: timerElapsedGe("last_main_burst", 6000),
              target_phase: "切武器爆发",
            },
            {
              label: "主武器基础循环完成",
              condition_expr: {
                type: "and",
                children: [counterGe("main_wp4_count", 1), counterGe("main_wp2_count", 1)],
              },
              target_phase: "副武器循环",
            },
          ],
          fallback_transition: { type: "stay" },
          skills: [
            slot("virt_gs4", "主武器 4：优先释放", 1, {
              protectedRelease: true,
              postActions: [incrementCounter("main_wp4_count")],
            }),
            slot("virt_gs2", "主武器 2：循环填充", 2, {
              postActions: [incrementCounter("main_wp2_count")],
            }),
            slot("virt_shatter", "职业爆发：有资源时释放", 3, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
              postActions: [recordTimer("last_main_burst")],
            }),
          ],
        },
        {
          name: "副武器循环",
          complete_when: "none_ready",
          entry_actions: [setMarker("weapon", "alt")],
          transition_rules: [
            {
              label: "副武器循环完成",
              condition_expr: counterGe("alt_twp3_count", 1),
              target_phase: "主武器起手修正",
            },
          ],
          fallback_transition: { type: "next" },
          skills: [
            slot("virt_focus4", "副武器 4：循环补位", 1, {
              protectedRelease: true,
              postActions: [incrementCounter("alt_twp3_count")],
            }),
            slot("virt_focus5", "副武器 5：可用则释放", 2, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
              postActions: [incrementCounter("alt_twp5_count")],
            }),
          ],
        },
        {
          name: "主武器起手修正",
          complete_when: "any_fired",
          entry_actions: [],
          transition_rules: [],
          fallback_transition: { type: "next" },
          skills: [
            slot("virt_weapon_swap", "切回主武器", 1, {
              protectedRelease: true,
              postActions: [setMarker("weapon", "main")],
            }),
          ],
        },
        {
          name: "切武器爆发",
          complete_when: "none_ready",
          entry_actions: [],
          transition_rules: [],
          fallback_transition: { type: "phase", target_phase: "主武器循环" },
          skills: [
            slot("virt_shatter", "爆发技能：等待状态条完成", 1, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
              postActions: [recordTimer("last_main_burst")],
            }),
            slot("virt_gs4", "爆发后补主武器 4", 2, {
              protectedRelease: true,
              postActions: [incrementCounter("main_wp4_count")],
            }),
          ],
        },
      ],
      assist_lanes: [],
    },
  },
  condi_quickness_firebrand: {
    label: "症状急速燃火",
    value: "condi_quickness_firebrand",
    description: "主循环处理 F1/火炬/武器刷新，咒语类技能放入辅助 Lane。",
    rotation: {
      name: "症状急速燃火 - 状态机模板",
      poll_interval_ms: 80,
      max_cycles: 0,
      state_schema: {
        markers: [
          {
            id: "weapon",
            name: "当前武器组",
            initial_value: "unknown",
            allowed_values: ["unknown", "main", "torch"],
          },
          {
            id: "f1_state",
            name: "F1 状态",
            initial_value: "closed",
            allowed_values: ["closed", "open"],
          },
        ],
        timers: [
          { id: "last_f1_burst", name: "F1 爆发时间", reset_on_cycle_start: true },
          { id: "last_torch4", name: "火炬 4 时间", reset_on_cycle_start: true },
          { id: "last_wp5_refresh", name: "武器 5 刷新", reset_on_cycle_start: true },
          { id: "last_wp4_refresh", name: "武器 4 刷新", reset_on_cycle_start: true },
          { id: "last_ty2_assist", name: "辅助 TY2", reset_on_cycle_start: true },
          { id: "last_ty3_assist", name: "辅助 TY3", reset_on_cycle_start: true },
          { id: "last_ty1_assist", name: "辅助 TY1", reset_on_cycle_start: true },
        ],
        counters: [
          {
            id: "f1_pages_used",
            name: "F1 书页计数",
            initial_value: 0,
            reset_on_phase_entry: true,
            reset_on_cycle_start: true,
          },
        ],
      },
      phases: [
        {
          name: "常规优先级",
          complete_when: "none_ready",
          entry_actions: [],
          transition_rules: [
            {
              label: "F1 爆发到期",
              condition_expr: timerElapsedGe("last_f1_burst", 8000),
              target_phase: "F1 打开处理",
            },
            {
              label: "火炬窗口到期",
              condition_expr: timerElapsedGe("last_torch4", 7000),
              target_phase: "火炬循环",
            },
          ],
          fallback_transition: { type: "stay" },
          skills: [
            slot("fb_priority_1", "常规优先级 1", 1),
            slot("fb_priority_2", "常规优先级 2", 2),
            slot("fb_axe2", "主武器 2：填充/症状", 3),
          ],
        },
        {
          name: "F1 打开处理",
          complete_when: "none_ready",
          entry_actions: [setMarker("f1_state", "open")],
          transition_rules: [
            {
              label: "书页释放完成",
              condition_expr: counterGe("f1_pages_used", 2),
              target_phase: "主武器循环",
            },
          ],
          fallback_transition: { type: "next" },
          skills: [
            slot("fb_f1_open", "打开 F1", 1, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
            }),
            slot("fb_f1_page2", "F1 书页 2", 2, {
              protectedRelease: true,
              postActions: [incrementCounter("f1_pages_used")],
            }),
            slot("fb_f1_page4", "F1 书页 4", 3, {
              protectedRelease: true,
              postActions: [incrementCounter("f1_pages_used"), recordTimer("last_f1_burst")],
            }),
          ],
        },
        {
          name: "主武器循环",
          complete_when: "none_ready",
          entry_actions: [setMarker("weapon", "main")],
          transition_rules: [
            {
              label: "武器 5 刷新",
              condition_expr: timerElapsedGe("last_wp5_refresh", 10000),
              target_phase: "定时刷新",
            },
            {
              label: "切火炬窗口",
              condition_expr: timerElapsedGe("last_torch4", 7000),
              target_phase: "切武器处理",
            },
          ],
          fallback_transition: { type: "stay" },
          skills: [
            slot("fb_axe2", "主武器 2", 1),
            slot("fb_wp4_refresh", "武器 4 刷新", 2, {
              protectedRelease: true,
              postActions: [recordTimer("last_wp4_refresh")],
            }),
            slot("fb_wp5_refresh", "武器 5 刷新", 3, {
              protectedRelease: true,
              postActions: [recordTimer("last_wp5_refresh")],
            }),
          ],
        },
        {
          name: "火炬循环",
          complete_when: "none_ready",
          entry_actions: [setMarker("weapon", "torch")],
          transition_rules: [],
          fallback_transition: { type: "phase", target_phase: "主武器循环" },
          skills: [
            slot("fb_torch4", "火炬 4：状态条保护", 1, {
              protectedRelease: true,
              attemptPolicy: burstAttemptPolicy,
              postActions: [recordTimer("last_torch4")],
            }),
            slot("fb_torch5", "火炬 5：可用则释放", 2, {
              protectedRelease: true,
            }),
          ],
        },
        {
          name: "切武器处理",
          complete_when: "any_fired",
          entry_actions: [],
          transition_rules: [],
          fallback_transition: { type: "phase", target_phase: "火炬循环" },
          skills: [
            slot("fb_weapon_swap", "切换武器组", 1, {
              protectedRelease: true,
              postActions: [setMarker("weapon", "torch")],
            }),
          ],
        },
        {
          name: "定时刷新",
          complete_when: "none_ready",
          entry_actions: [],
          transition_rules: [],
          fallback_transition: { type: "phase", target_phase: "常规优先级" },
          skills: [
            slot("fb_wp5_refresh", "刷新武器 5", 1, {
              protectedRelease: true,
              postActions: [recordTimer("last_wp5_refresh")],
            }),
            slot("fb_wp4_refresh", "刷新武器 4", 2, {
              protectedRelease: true,
              postActions: [recordTimer("last_wp4_refresh")],
            }),
          ],
        },
      ],
      assist_lanes: [
        {
          id: "firebrand_mantra_assist",
          name: "咒语/补充技能辅助 Lane",
          enabled: true,
          check_interval_ms: 250,
          interrupt_policy: "complete_wait",
          skills: [
            slot("fb_ty2_assist", "TY2：辅助补位", 1, {
              condition: timerElapsedGe("last_ty2_assist", 4500),
              postActions: [recordTimer("last_ty2_assist")],
            }),
            slot("fb_ty3_assist", "TY3：辅助补位", 2, {
              condition: timerElapsedGe("last_ty3_assist", 6500),
              postActions: [recordTimer("last_ty3_assist")],
            }),
            slot("fb_ty1_assist", "TY1：最低优先补位", 3, {
              condition: timerElapsedGe("last_ty1_assist", 3500),
              postActions: [recordTimer("last_ty1_assist")],
            }),
          ],
        },
      ],
    },
  },
};

export const cyclePresetOptions: CyclePresetOption[] = Object.values(presets).map(
  ({ label, value, description }) => ({ label, value, description }),
);

export function buildCyclePreset(id: CyclePresetId): CycleConfig {
  return JSON.parse(JSON.stringify(presets[id].rotation)) as CycleConfig;
}

export function getCyclePresetLabel(id: CyclePresetId): string {
  return presets[id].label;
}
