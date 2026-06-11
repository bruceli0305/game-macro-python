<script setup lang="ts">
import { computed, reactive, ref, onMounted, onUnmounted } from "vue";
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NSelect,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from "naive-ui";
import { IconPlus, IconDeviceFloppy } from "@tabler/icons-vue";
import AssistLanePanel from "../components/editor/AssistLanePanel.vue";
import ObserverLanePanel from "../components/editor/ObserverLanePanel.vue";
import PhaseLane from "../components/editor/PhaseLane.vue";
import RuntimeStatePanel from "../components/editor/RuntimeStatePanel.vue";
import SkillEditModal from "../components/editor/SkillEditModal.vue";
import ProfileIssueSummary from "../components/common/ProfileIssueSummary.vue";
import EngineControlBar from "../components/engine/EngineControlBar.vue";
import ExecLogViewer from "../components/engine/ExecLogViewer.vue";
import SkillStatusGrid from "../components/engine/SkillStatusGrid.vue";
import { useProfile, withProfileRotations } from "../composables/useProfile";
import { useEngineStore } from "../stores/engine";
import {
  firstProfileError,
  validateProfileForEngineStart,
  validateProfileForSave,
} from "../utils/profile-validation";
import type {
  AssistLaneConfig,
  CycleConfig,
  PhaseFallbackTransition,
  RuntimeAction,
  CycleStateSchema,
  ObserverLaneConfig,
  SkillSlot,
  SkillSlotRole,
} from "../types/cycle";
import type { Expr } from "../types/ast";
import type { Point } from "../types/point";
import type { Profile } from "../types/profile";
import type { Skill } from "../types/skill";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

const engineStore = useEngineStore();
const { loadActiveProfile, saveActiveProfile } = useProfile();
const message = useMessage();

const defaultConfig: CycleConfig = {
  name: "我的循环",
  phases: [{
    name: "",
    skills: [],
    complete_when: "none_ready",
    entry_actions: [],
    transition_rules: [],
    fallback_transition: { type: "next" },
  }],
  observer_lanes: [],
  assist_lanes: [],
  poll_interval_ms: 100,
  max_cycles: 0,
  state_schema: { markers: [], timers: [], counters: [] },
};
const config = reactive<CycleConfig>(JSON.parse(JSON.stringify(defaultConfig)));

const savedSkills = ref<Skill[]>([]);
const skillList = ref<{ id: string; name: string }[]>([]);
const savedPoints = ref<Point[]>([]);
const pointList = ref<{ id: string; name: string }[]>([]);
const collapsedPhases = ref<Set<number>>(new Set());
const loadedProfile = ref<Profile | null>(null);
const showSideDrawer = ref(false);
const workspace = ref<"phases" | "observer" | "assist">("phases");
const selectedPhaseIndex = ref(0);
const markerList = computed(() =>
  (config.state_schema?.markers ?? []).map((marker) => ({
    id: marker.id,
    name: marker.name || marker.id,
    allowed_values: marker.allowed_values ?? [],
  }))
);
const timerList = computed(() =>
  (config.state_schema?.timers ?? []).map((timer) => ({ id: timer.id, name: timer.name || timer.id }))
);
const counterList = computed(() =>
  (config.state_schema?.counters ?? []).map((counter) => ({
    id: counter.id,
    name: counter.name || counter.id,
  }))
);
const phaseOptions = computed(() =>
  config.phases
    .map((phase, index) => {
      const name = phase.name.trim();
      return name ? { id: name, name: `${index + 1}. ${name}` } : null;
    })
    .filter((phase): phase is { id: string; name: string } => phase !== null)
);
const showEditModal = ref(false);
const editingSlot = reactive<SkillSlot>({
  skill_id: "",
  priority: 1,
  label: "",
  slot_role: "mandatory",
  condition_expr: null,
  readiness_expr: null,
  readiness_policy: "required",
  start_expr: null,
  complete_expr: null,
  override_cast_ms: null,
  protected_release: false,
  attempt_policy: null,
  post_actions: [],
});
const editingPhaseIdx = ref(-1);
const editingSlotIdx = ref(-1);
const editingAssistLaneIdx = ref(-1);
const editingScope = ref<"phase" | "assist">("phase");

const skillNames = ref<Record<string, string>>({});
const skillMeta = ref<Record<string, SkillCardMeta>>({});

const phaseCount = computed(() => config.phases.length);
const observerLaneCount = computed(() => config.observer_lanes?.length ?? 0);
const assistLaneCount = computed(() => config.assist_lanes?.length ?? 0);
const slotCount = computed(() =>
  config.phases.reduce((count, phase) => count + phase.skills.length, 0) +
  (config.observer_lanes ?? []).reduce((count, lane) => count + lane.actions.length, 0) +
  (config.assist_lanes ?? []).reduce((count, lane) => count + lane.skills.length, 0)
);
const markerCount = computed(() => config.state_schema?.markers?.length ?? 0);
const timerCount = computed(() => config.state_schema?.timers?.length ?? 0);
const counterCount = computed(() => config.state_schema?.counters?.length ?? 0);
const engineStartIssues = computed(() => {
  if (!loadedProfile.value) return [];
  const next = withProfileRotations(
    loadedProfile.value,
    [JSON.parse(JSON.stringify(config)) as CycleConfig]
  );
  return validateProfileForEngineStart(next);
});
const selectedPhase = computed(() => config.phases[selectedPhaseIndex.value] ?? null);

const completeLabels: Record<string, string> = {
  all_fired: "全部释放",
  any_fired: "任一释放",
  none_ready: "都未就绪",
  always: "立即进入",
};
const completeWhenOptions = [
  { label: "都未就绪（推荐）", value: "none_ready" },
  { label: "全部释放", value: "all_fired" },
  { label: "任一释放", value: "any_fired" },
  { label: "立即进入", value: "always" },
];
const roleLabels: Record<SkillSlotRole, string> = {
  mandatory: "必放",
  priority: "优先",
  filler: "填充",
};

function phaseRoleCounts(phase: CycleConfig["phases"][number]) {
  return phase.skills.reduce(
    (counts, slot) => {
      const role = slot.slot_role ?? "mandatory";
      counts[role] += 1;
      return counts;
    },
    { mandatory: 0, priority: 0, filler: 0 } as Record<SkillSlotRole, number>,
  );
}

function phaseDisplayName(phase: CycleConfig["phases"][number], index: number): string {
  return phase.name.trim() || `阶段 ${index + 1}`;
}

function completeLabel(value: string): string {
  return completeLabels[value] ?? value;
}
function setCompleteWhen(value: string) {
  if (selectedPhase.value) {
    selectedPhase.value.complete_when = value as CycleConfig["phases"][number]["complete_when"];
  }
}

function skillDisplayName(skillId: string): string {
  return skillNames.value[skillId] || skillId || "未选择技能";
}

function pointDisplayName(pointId: string): string {
  return pointList.value.find((point) => point.id === pointId)?.name || pointId || "未选择点位";
}

function markerDisplayName(markerId: string): string {
  return markerList.value.find((marker) => marker.id === markerId)?.name || markerId || "未选择标记";
}

function timerDisplayName(timerId: string): string {
  return timerList.value.find((timer) => timer.id === timerId)?.name || timerId || "未选择时间";
}

function counterDisplayName(counterId: string): string {
  return counterList.value.find((counter) => counter.id === counterId)?.name || counterId || "未选择计数器";
}

function exprSummary(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "无条件";
  const exprValue = value as Expr;
  return summarizeExpr(exprValue);
}

function summarizeExpr(value: Expr): string {
  switch (value.type) {
    case "and":
      return value.children.length > 0
        ? value.children.map(summarizeExpr).join(" 且 ")
        : "AND 未配置子条件";
    case "or":
      return value.children.length > 0
        ? value.children.map(summarizeExpr).join(" 或 ")
        : "OR 未配置子条件";
    case "not":
      return `非（${summarizeExpr(value.child)}）`;
    case "const":
      return value.value ? "始终满足" : "永不满足";
    case "pixel_point":
      return `${pointDisplayName(value.point_id)} 颜色匹配，容差 ${value.tolerance}`;
    case "pixel_point_not_match":
      return `${pointDisplayName(value.point_id)} 颜色不匹配，容差 ${value.tolerance}`;
    case "pixel_point_black":
      return `${pointDisplayName(value.point_id)} 变黑，阈值 ${value.tolerance}`;
    case "pixel_point_not_black":
      return `${pointDisplayName(value.point_id)} 非黑，阈值 ${value.tolerance}`;
    case "pixel_point_nearest":
      return `${pointDisplayName(value.expected_point_id)} 是候选中最近颜色，最大差值 ${value.max_delta}，最小间隔 ${value.min_margin}`;
    case "pixel_skill":
      return `${skillDisplayName(value.skill_id)} 图标匹配，容差 ${value.tolerance}`;
    case "pixel_skill_not_match":
      return `${skillDisplayName(value.skill_id)} 图标不匹配，容差 ${value.tolerance}`;
    case "pixel_skill_black":
      return `${skillDisplayName(value.skill_id)} 图标变黑，阈值 ${value.tolerance}`;
    case "pixel_skill_not_black":
      return `${skillDisplayName(value.skill_id)} 图标非黑，阈值 ${value.tolerance}`;
    case "cast_bar_changed":
      return `${pointDisplayName(value.point_id)} 状态条变化，容差 ${value.tolerance}`;
    case "cast_bar_roi_changed":
      return "施法条 ROI 发生变化";
    case "cast_bar_roi_border_visible":
      return "施法条 ROI 边框出现";
    case "cast_bar_roi_gone":
      return "施法条 ROI 消失";
    case "skill_metric_ge":
      return `${skillDisplayName(value.skill_id)} 的 ${value.metric} >= ${value.count}`;
    case "marker_eq":
      return `${markerDisplayName(value.marker_id)} = ${value.value}`;
    case "marker_ne":
      return `${markerDisplayName(value.marker_id)} != ${value.value}`;
    case "timer_elapsed_ge":
      return `${timerDisplayName(value.timer_id)} 已超过 ${value.ms}ms`;
    case "timer_elapsed_lt":
      return `${timerDisplayName(value.timer_id)} 未超过 ${value.ms}ms`;
    case "counter_ge":
      return `${counterDisplayName(value.counter_id)} >= ${value.value}`;
    case "counter_eq":
      return `${counterDisplayName(value.counter_id)} = ${value.value}`;
    case "counter_gt":
      return `${counterDisplayName(value.counter_id)} > ${value.value}`;
  }
}

function runtimeActionSummary(action: RuntimeAction): string {
  switch (action.type) {
    case "set_marker":
      return `设置 ${markerDisplayName(action.marker_id)} = ${action.value}`;
    case "clear_marker":
      return `清除 ${markerDisplayName(action.marker_id)}`;
    case "record_timer":
      return `记录 ${timerDisplayName(action.timer_id)}`;
    case "reset_timer":
      return `重置 ${timerDisplayName(action.timer_id)}`;
    case "increment_counter":
      return `${counterDisplayName(action.counter_id)} + ${action.by}`;
    case "set_counter":
      return `设置 ${counterDisplayName(action.counter_id)} = ${action.value}`;
    case "reset_counter":
      return `重置 ${counterDisplayName(action.counter_id)}`;
  }
}

function fallbackSummary(fallback: PhaseFallbackTransition | null | undefined): string {
  if (!fallback || fallback.type === "next") return "未命中跳转规则时进入下一阶段";
  if (fallback.type === "stay") return "未命中跳转规则时停留当前阶段";
  return `未命中跳转规则时跳转到 ${fallback.target_phase}`;
}

function slotTriggerKey(slot: SkillSlot): string {
  return skillMeta.value[slot.skill_id]?.triggerKey || "-";
}

function slotAttemptSummary(slot: SkillSlot): string {
  const policy = slot.attempt_policy;
  if (!policy) return "使用全局确认策略";
  const completeWindow =
    policy.complete_timeout_ms > 0 ? `${policy.complete_timeout_ms}ms` : "按技能读条/全局配置";
  return `最多 ${policy.max_attempts} 次；施法确认窗口 ${policy.start_timeout_ms}ms；完成确认窗口 ${completeWindow}`;
}

function roleSlots(role: SkillSlotRole): SkillSlot[] {
  return [
    ...(selectedPhase.value?.skills.filter((slot) => (slot.slot_role ?? "mandatory") === role) ?? []),
  ].sort((a, b) => a.priority - b.priority);
}

function clampSelectedPhase() {
  if (config.phases.length === 0) {
    selectedPhaseIndex.value = 0;
    return;
  }
  selectedPhaseIndex.value = Math.min(
    Math.max(selectedPhaseIndex.value, 0),
    config.phases.length - 1,
  );
}

function selectPhase(index: number) {
  selectedPhaseIndex.value = index;
  workspace.value = "phases";
}

async function loadEditorProfile() {
  try {
    const p = await loadActiveProfile();
    loadedProfile.value = p;
    Object.assign(config, JSON.parse(JSON.stringify(defaultConfig)) as CycleConfig);
    if (p?.rotations?.length > 0) {
      Object.assign(config, p.rotations[0]);
      config.observer_lanes ??= [];
      config.assist_lanes ??= [];
    }
    savedSkills.value = p?.skills?.skills || [];
    skillList.value = savedSkills.value.map((s) => ({ id: s.id, name: s.name || s.id }));
    skillNames.value = Object.fromEntries(savedSkills.value.map((s) => [s.id, s.name || s.id]));
    skillMeta.value = Object.fromEntries(
      savedSkills.value.map((s) => [
        s.id,
        {
          triggerKey: s.trigger_key,
          readbarMs: s.cast.readbar_ms,
          cooldownMs: s.cooldown_ms || s.cast.cooldown_ms,
          shotsPerCycle: s.shots_per_cycle,
        },
      ]),
    );
    savedPoints.value = p?.points?.points || [];
    pointList.value = savedPoints.value.map((p) => ({ id: p.id, name: p.name || p.id }));
    clampSelectedPhase();
  } catch { /* 棣栨 */ }
}

function onActiveProfileChanged() {
  void loadEditorProfile();
}

onMounted(() => {
  window.addEventListener("profile:active-changed", onActiveProfileChanged);
  void loadEditorProfile();
});
onUnmounted(() => window.removeEventListener("profile:active-changed", onActiveProfileChanged));

function addPhase() {
  config.phases.push({
    name: "",
    skills: [],
    complete_when: "none_ready",
    entry_actions: [],
    transition_rules: [],
    fallback_transition: { type: "next" },
  });
  selectedPhaseIndex.value = config.phases.length - 1;
  workspace.value = "phases";
}
function removePhase(i: number) {
  config.phases.splice(i, 1);
  clampSelectedPhase();
}
function addSlot(pi: number, slotRole: SkillSlotRole = "mandatory") {
  config.phases[pi].skills.push({
    skill_id: "",
    priority: config.phases[pi].skills.length + 1,
    label: "",
    slot_role: slotRole,
    condition_expr: null,
    readiness_expr: null,
    readiness_policy: "required",
    start_expr: null,
    complete_expr: null,
    override_cast_ms: null,
    protected_release: false,
    attempt_policy: null,
    post_actions: [],
  });
}
function removeSlot(pi: number, si: number) { config.phases[pi].skills.splice(si, 1); }

function createEmptySlot(priority: number, slotRole: SkillSlotRole = "mandatory"): SkillSlot {
  return {
    skill_id: "",
    priority,
    label: "",
    slot_role: slotRole,
    condition_expr: null,
    readiness_expr: null,
    readiness_policy: "required",
    start_expr: null,
    complete_expr: null,
    override_cast_ms: null,
    protected_release: false,
    attempt_policy: null,
    post_actions: [],
  };
}

function addAssistSlot(laneIndex: number) {
  const lane = config.assist_lanes?.[laneIndex];
  if (!lane) return;
  lane.skills.push(createEmptySlot(lane.skills.length + 1, "priority"));
}

function removeAssistSlot(laneIndex: number, slotIndex: number) {
  config.assist_lanes?.[laneIndex]?.skills.splice(slotIndex, 1);
}

function openEdit(pi: number, si: number) {
  editingScope.value = "phase";
  editingPhaseIdx.value = pi;
  editingSlotIdx.value = si;
  editingAssistLaneIdx.value = -1;
  Object.assign(editingSlot, JSON.parse(JSON.stringify(config.phases[pi].skills[si])));
  showEditModal.value = true;
}

function openAssistEdit(laneIndex: number, slotIndex: number) {
  const lane = config.assist_lanes?.[laneIndex];
  const slot = lane?.skills[slotIndex];
  if (!slot) return;
  editingScope.value = "assist";
  editingPhaseIdx.value = -1;
  editingAssistLaneIdx.value = laneIndex;
  editingSlotIdx.value = slotIndex;
  Object.assign(editingSlot, JSON.parse(JSON.stringify(slot)));
  showEditModal.value = true;
}

function onSaved(slot: SkillSlot) {
  if (editingScope.value === "assist" && editingAssistLaneIdx.value >= 0 && editingSlotIdx.value >= 0) {
    const lane = config.assist_lanes?.[editingAssistLaneIdx.value];
    if (lane) lane.skills[editingSlotIdx.value] = slot;
    return;
  }
  if (editingScope.value === "phase" && editingPhaseIdx.value >= 0 && editingSlotIdx.value >= 0) {
    config.phases[editingPhaseIdx.value].skills[editingSlotIdx.value] = slot;
  }
}
function toggleCollapse(i: number) {
  if (collapsedPhases.value.has(i)) collapsedPhases.value.delete(i);
  else collapsedPhases.value.add(i);
}

function updateStateSchema(value: CycleStateSchema) {
  config.state_schema = value;
}

function updateAssistLanes(value: AssistLaneConfig[]) {
  config.assist_lanes = value;
}

function updateObserverLanes(value: ObserverLaneConfig[]) {
  config.observer_lanes = value;
}

async function saveProfile() {
  try {
    const profile = await loadActiveProfile();
    const next = withProfileRotations(profile, [JSON.parse(JSON.stringify(config)) as CycleConfig]);
    const error = firstProfileError(validateProfileForSave(next));
    if (error) {
      message.error(error);
      return;
    }
    await saveActiveProfile(next);
    loadedProfile.value = next;
    message.success("循环配置已保存");
  } catch (e) {
    console.error(e);
    message.error("保存失败，请检查技能和点位引用");
  }
}
</script>

<template>
  <div class="cycle-editor-page flex h-full min-h-0 flex-col gap-4">
    <header class="cycle-editor-header flex flex-none flex-wrap items-center justify-between gap-3">
      <div class="cycle-editor-title min-w-0">
        <h1 class="text-xl font-bold leading-tight">循环编辑器</h1>
        <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-400">
          <n-tag size="small" :bordered="false">阶段 {{ phaseCount }}</n-tag>
          <n-tag size="small" :bordered="false">观察 {{ observerLaneCount }}</n-tag>
          <n-tag size="small" :bordered="false">辅助 {{ assistLaneCount }}</n-tag>
          <n-tag size="small" :bordered="false">技能槽 {{ slotCount }}</n-tag>
          <span class="truncate">{{ config.name || "未命名循环" }}</span>
        </div>
      </div>
      <div class="cycle-editor-actions flex flex-wrap items-center gap-2">
        <div class="cycle-state-summary" aria-label="运行状态摘要">
          <n-tag size="small" :bordered="false">标记 {{ markerCount }}</n-tag>
          <n-tag size="small" :bordered="false">时间 {{ timerCount }}</n-tag>
          <n-tag size="small" :bordered="false">计数器 {{ counterCount }}</n-tag>
        </div>
        <n-button size="small" @click="showSideDrawer = true">
          状态 / 监控
        </n-button>
        <n-button size="small" @click="saveProfile">
          <template #icon><IconDeviceFloppy /></template>
          保存
        </n-button>
        <n-button size="small" type="primary" @click="addPhase">
          <template #icon><IconPlus /></template>
          添加阶段
        </n-button>
      </div>
    </header>

    <nav class="cycle-workspace-tabs" aria-label="循环编辑工作区">
      <button
        class="cycle-workspace-tab"
        :class="{ active: workspace === 'phases' }"
        type="button"
        @click="workspace = 'phases'"
      >
        <span>主循环</span>
        <small>{{ phaseCount }} 阶段</small>
      </button>
      <button
        class="cycle-workspace-tab"
        :class="{ active: workspace === 'observer' }"
        type="button"
        @click="workspace = 'observer'"
      >
        <span>状态识别</span>
        <small>{{ observerLaneCount }} Lane</small>
      </button>
      <button
        class="cycle-workspace-tab"
        :class="{ active: workspace === 'assist' }"
        type="button"
        @click="workspace = 'assist'"
      >
        <span>后台动作</span>
        <small>{{ assistLaneCount }} Lane</small>
      </button>
    </nav>

    <div v-if="workspace === 'phases'" class="cycle-workbench">
      <aside class="phase-navigator" aria-label="阶段导航">
        <div class="phase-navigator-header">
          <div>
            <h2>阶段导航</h2>
            <p>选择一个阶段后在右侧编辑</p>
          </div>
          <n-button size="tiny" secondary @click="addPhase">
            <template #icon><IconPlus :size="14" /></template>
            新阶段
          </n-button>
        </div>

        <div class="phase-nav-list">
          <button
            v-for="(phase, pi) in config.phases"
            :key="pi"
            class="phase-nav-item"
            :class="{
              active: selectedPhaseIndex === pi,
              running: engineStore.isRunning && engineStore.currentPhase === pi,
            }"
            type="button"
            @click="selectPhase(pi)"
          >
            <span class="phase-nav-index">P{{ pi + 1 }}</span>
            <span class="phase-nav-main">
              <strong>{{ phaseDisplayName(phase, pi) }}</strong>
              <em>{{ completeLabel(phase.complete_when) }}</em>
            </span>
            <span class="phase-nav-counts">
              <span>必 {{ phaseRoleCounts(phase).mandatory }}</span>
              <span>优 {{ phaseRoleCounts(phase).priority }}</span>
              <span>填 {{ phaseRoleCounts(phase).filler }}</span>
            </span>
          </button>
        </div>
      </aside>

      <section class="phase-focus">
        <div class="phase-focus-header">
          <div>
            <h2>阶段编辑</h2>
            <p v-if="selectedPhase">
              P{{ selectedPhaseIndex + 1 }} · {{ phaseDisplayName(selectedPhase, selectedPhaseIndex) }}
            </p>
            <p v-else>当前没有阶段</p>
          </div>
          <div class="phase-focus-actions">
            <n-button
              size="small"
              :disabled="selectedPhaseIndex <= 0"
              @click="selectPhase(selectedPhaseIndex - 1)"
            >
              上一阶段
            </n-button>
            <n-button
              size="small"
              :disabled="selectedPhaseIndex >= config.phases.length - 1"
              @click="selectPhase(selectedPhaseIndex + 1)"
            >
              下一阶段
            </n-button>
          </div>
        </div>

        <div class="phase-focus-body">
          <section v-if="selectedPhase" class="phase-rule-summary">
            <div class="summary-section">
              <div class="summary-section-title">阶段完成</div>
              <div class="summary-grid">
                <div class="summary-item">
                  <span>完成方式</span>
                  <n-select
                    v-if="selectedPhase"
                    :value="selectedPhase.complete_when"
                    :options="completeWhenOptions"
                    size="small"
                    style="width: 160px"
                    @update:value="setCompleteWhen"
                  />
                </div>
                <div class="summary-item">
                  <span>参与完成</span>
                  <strong>
                    必放 {{ phaseRoleCounts(selectedPhase).mandatory }}
                    <template v-if="phaseRoleCounts(selectedPhase).mandatory === 0">
                      · 无必放时由非填充决定
                    </template>
                  </strong>
                </div>
                <div class="summary-item">
                  <span>入口动作</span>
                  <strong>
                    <template v-if="(selectedPhase.entry_actions ?? []).length > 0">
                      {{ (selectedPhase.entry_actions ?? []).map(runtimeActionSummary).join("；") }}
                    </template>
                    <template v-else>无</template>
                  </strong>
                </div>
                <div class="summary-item">
                  <span>Fallback</span>
                  <strong>{{ fallbackSummary(selectedPhase.fallback_transition) }}</strong>
                </div>
              </div>
            </div>

            <div class="summary-section">
              <div class="summary-section-title">帧级候选与优先级</div>
              <p class="summary-section-note">
                每个 tick 先读取当前帧状态，再按顺位从小到大检查候选技能；只有形态、冷却、次数和触发条件都满足时才会发送按键。
              </p>
              <div class="summary-role-list">
                <div
                  v-for="role in (['mandatory', 'priority', 'filler'] as SkillSlotRole[])"
                  :key="role"
                  class="summary-role"
                >
                  <div class="summary-role-title">
                    <span>{{ roleLabels[role] }}</span>
                    <em>{{ roleSlots(role).length }}</em>
                  </div>
                  <div v-if="roleSlots(role).length === 0" class="summary-empty">
                    无{{ roleLabels[role] }}技能
                  </div>
                  <div v-else class="summary-skill-list">
                    <article
                      v-for="slot in roleSlots(role)"
                      :key="`${role}-${slot.priority}-${slot.skill_id}`"
                      class="summary-skill"
                    >
                      <header>
                        <strong>{{ skillDisplayName(slot.skill_id) }}</strong>
                        <span>按键 {{ slotTriggerKey(slot) }} · 顺位 {{ slot.priority }}</span>
                      </header>
                      <dl>
                        <div>
                          <dt>硬条件</dt>
                          <dd>{{ exprSummary(slot.condition_expr) }}</dd>
                        </div>
                        <div>
                          <dt>就绪信号</dt>
                          <dd>
                            {{ exprSummary(slot.readiness_expr) }}
                            · {{ slot.readiness_policy === "advisory" ? "仅记录" : "必须满足" }}
                          </dd>
                        </div>
                        <div>
                          <dt>施法确认</dt>
                          <dd>{{ exprSummary(slot.start_expr) }}</dd>
                        </div>
                        <div>
                          <dt>完成确认</dt>
                          <dd>{{ exprSummary(slot.complete_expr) }}</dd>
                        </div>
                        <div>
                          <dt>确认策略</dt>
                          <dd>{{ slotAttemptSummary(slot) }}</dd>
                        </div>
                      </dl>
                    </article>
                  </div>
                </div>
              </div>
            </div>

            <div class="summary-section">
              <div class="summary-section-title">跳转出口</div>
              <div v-if="(selectedPhase.transition_rules ?? []).length === 0" class="summary-empty">
                无显式跳转规则，阶段完成后使用 Fallback。
              </div>
              <div v-else class="summary-transition-list">
                <article
                  v-for="(rule, ruleIndex) in selectedPhase.transition_rules"
                  :key="`${ruleIndex}-${rule.label}`"
                  class="summary-transition"
                >
                  <strong>{{ rule.label || `规则 ${ruleIndex + 1}` }}</strong>
                  <span>如果 {{ exprSummary(rule.condition_expr) }}，跳转到 {{ rule.target_phase || "未设置目标阶段" }}</span>
                </article>
              </div>
            </div>
          </section>

          <PhaseLane
            v-if="selectedPhase"
            :key="selectedPhaseIndex"
            :phase="selectedPhase"
            :phase-index="selectedPhaseIndex"
            :skill-names="skillNames"
            :skill-meta="skillMeta"
            :skill-options="skillList"
            :point-options="pointList"
            :marker-options="markerList"
            :timer-options="timerList"
            :counter-options="counterList"
            :phase-options="phaseOptions"
            :collapsed="false"
            :style="engineStore.isRunning && engineStore.currentPhase === selectedPhaseIndex
              ? 'border-color: #18a058; box-shadow: 0 0 8px rgba(24,160,88,0.3)'
              : ''"
            @update:phase="(p: any) => config.phases[selectedPhaseIndex] = p"
            @remove="removePhase(selectedPhaseIndex)"
            @add-slot="(role) => addSlot(selectedPhaseIndex, role)"
            @edit-slot="(si: number) => openEdit(selectedPhaseIndex, si)"
            @remove-slot="(si: number) => removeSlot(selectedPhaseIndex, si)"
            @toggle-collapse="toggleCollapse(selectedPhaseIndex)"
          />

          <div v-else class="phase-empty-state">
            <h3>还没有阶段</h3>
            <p>创建阶段后再配置技能槽、跳转规则和完成条件。</p>
            <n-button size="small" type="primary" @click="addPhase">
              <template #icon><IconPlus /></template>
              添加阶段
            </n-button>
          </div>
        </div>
      </section>
    </div>

    <section v-else-if="workspace === 'observer'" class="workspace-panel">
      <div class="workspace-panel-header">
        <div>
          <h2>状态识别</h2>
          <p>只负责读取画面并写入标记、时间和计数器，不发送技能按键。</p>
        </div>
      </div>
      <ObserverLanePanel
        :lanes="config.observer_lanes ?? []"
        :skill-options="skillList"
        :point-options="pointList"
        :marker-options="markerList"
        :timer-options="timerList"
        :counter-options="counterList"
        @update:lanes="updateObserverLanes"
      />
    </section>

    <section v-else class="workspace-panel">
      <div class="workspace-panel-header">
        <div>
          <h2>后台动作</h2>
          <p>用于短 CD、增益和填充动作。主循环等待时才按 Lane 策略插入。</p>
        </div>
      </div>
      <AssistLanePanel
        :lanes="config.assist_lanes ?? []"
        :skill-names="skillNames"
        :skill-meta="skillMeta"
        @update:lanes="updateAssistLanes"
        @add-slot="addAssistSlot"
        @edit-slot="openAssistEdit"
        @remove-slot="removeAssistSlot"
      />
    </section>

    <button class="cycle-drawer-handle" type="button" @click="showSideDrawer = true">
      状态
    </button>

    <n-drawer
      v-model:show="showSideDrawer"
      placement="right"
      width="min(520px, calc(100vw - 48px))"
      :trap-focus="false"
      :block-scroll="false"
    >
      <n-drawer-content title="状态与运行监控" closable>
        <n-tabs type="segment" animated>
          <n-tab-pane name="state" tab="状态配置">
            <div class="drawer-stack">
              <RuntimeStatePanel
                :model-value="config.state_schema"
                @update:model-value="updateStateSchema"
              />
            </div>
          </n-tab-pane>

          <n-tab-pane name="monitor" tab="运行监控">
            <div class="drawer-stack">
              <section class="cycle-side-section p-4">
                <h2 class="mb-3 text-sm font-semibold text-gray-100">运行控制</h2>
                <ProfileIssueSummary
                  :issues="engineStartIssues"
                  title="启动检查"
                  :limit="4"
                />
                <EngineControlBar />
              </section>

              <section class="cycle-side-section cycle-side-fill flex min-h-0 flex-col overflow-hidden">
                <div class="cycle-side-header flex-none border-b border-white/10 px-4 py-3">
                  <h2 class="text-sm font-semibold text-gray-100">技能状态</h2>
                </div>
                <div class="cycle-side-body min-h-0 flex-1 overflow-auto p-2">
                  <SkillStatusGrid />
                </div>
              </section>

              <section class="cycle-side-section cycle-side-log flex min-h-0 flex-col overflow-hidden">
                <div class="cycle-side-header flex-none border-b border-white/10 px-4 py-3">
                  <h2 class="text-sm font-semibold text-gray-100">执行日志</h2>
                </div>
                <div class="cycle-side-body min-h-0 flex-1 overflow-auto p-2">
                  <ExecLogViewer />
                </div>
              </section>
            </div>
          </n-tab-pane>
        </n-tabs>
      </n-drawer-content>
    </n-drawer>

    <!-- 编辑弹窗 -->
    <SkillEditModal
      :show="showEditModal"
      :slot="editingSlot"
      :skill-options="skillList"
      :point-options="pointList"
      :marker-options="markerList"
      :timer-options="timerList"
      :counter-options="counterList"
      @update:show="showEditModal = $event"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.cycle-editor-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 16px;
}

.cycle-editor-header,
.cycle-editor-actions {
  display: flex;
  align-items: center;
}

.cycle-editor-header {
  flex: 0 0 auto;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.cycle-editor-title {
  min-width: 0;
}

.cycle-editor-actions {
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.cycle-state-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding-right: 4px;
}

.cycle-workspace-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  flex: 0 0 auto;
  gap: 8px;
}

.cycle-workspace-tab {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 3%);
  color: #d1d5db;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
}

.cycle-workspace-tab:hover,
.cycle-workspace-tab.active {
  border-color: rgb(94 234 212 / 40%);
  background: rgb(94 234 212 / 10%);
  color: #f9fafb;
}

.cycle-workspace-tab span {
  font-size: 13px;
  font-weight: 700;
}

.cycle-workspace-tab small {
  flex: 0 0 auto;
  color: #9ca3af;
  font-size: 11px;
}

.cycle-workbench {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  flex: 1 1 auto;
  min-height: 0;
  gap: 12px;
}

.phase-navigator,
.phase-focus,
.workspace-panel,
.cycle-side-section {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 2%);
}

.phase-navigator,
.phase-focus,
.workspace-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.phase-navigator-header,
.phase-focus-header,
.workspace-panel-header,
.cycle-side-header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  padding: 12px 16px;
}

.phase-navigator-header h2,
.phase-focus-header h2,
.workspace-panel-header h2 {
  color: #f3f4f6;
  font-size: 14px;
  font-weight: 700;
}

.phase-navigator-header p,
.phase-focus-header p,
.workspace-panel-header p {
  margin-top: 2px;
  color: #6b7280;
  font-size: 12px;
}

.phase-nav-list,
.phase-focus-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 10px;
}

.phase-rule-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
  border: 1px solid rgb(94 234 212 / 18%);
  border-radius: 6px;
  background: rgb(94 234 212 / 4%);
  padding: 12px;
}

.summary-section {
  min-width: 0;
}

.summary-section + .summary-section {
  border-top: 1px solid rgb(255 255 255 / 8%);
  padding-top: 10px;
}

.summary-section-title {
  margin-bottom: 8px;
  color: #ccfbf1;
  font-size: 12px;
  font-weight: 800;
}

.summary-section-note {
  margin: -2px 0 8px;
  color: #93a4b7;
  font-size: 12px;
  line-height: 1.5;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.summary-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 5px;
  background: rgb(0 0 0 / 12%);
  padding: 8px;
}

.summary-item span,
.summary-skill dt {
  color: #8b949e;
  font-size: 11px;
}

.summary-item strong {
  overflow-wrap: anywhere;
  color: #e5e7eb;
  font-size: 12px;
  font-weight: 600;
}

.summary-role-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-role {
  min-width: 0;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 5px;
  background: rgb(0 0 0 / 12%);
  padding: 8px;
}

.summary-role-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.summary-role-title span {
  color: #f3f4f6;
  font-size: 12px;
  font-weight: 800;
}

.summary-role-title em {
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
  color: #9ca3af;
  font-size: 11px;
  font-style: normal;
  padding: 1px 7px;
}

.summary-empty {
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 5px;
  color: #6b7280;
  font-size: 12px;
  padding: 8px;
  text-align: center;
}

.summary-skill-list,
.summary-transition-list {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
}

.summary-skill,
.summary-transition {
  min-width: 0;
  border-radius: 5px;
  background: rgb(255 255 255 / 4%);
  padding: 8px;
}

.summary-skill header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.summary-skill header strong,
.summary-transition strong {
  overflow: hidden;
  color: #f9fafb;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-skill header span {
  flex: 0 0 auto;
  color: #9ca3af;
  font-size: 11px;
}

.summary-skill dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
  margin: 0;
}

.summary-skill dl div {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 6px;
}

.summary-skill dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: #d1d5db;
  font-size: 11px;
}

.summary-transition {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-transition span {
  overflow-wrap: anywhere;
  color: #d1d5db;
  font-size: 12px;
}

.phase-nav-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.phase-nav-item {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 6px;
  background: rgb(0 0 0 / 12%);
  color: #d1d5db;
  padding: 9px;
  text-align: left;
  cursor: pointer;
}

.phase-nav-item:hover,
.phase-nav-item.active {
  border-color: rgb(94 234 212 / 36%);
  background: rgb(94 234 212 / 9%);
}

.phase-nav-item.running {
  border-color: rgb(24 160 88 / 70%);
  box-shadow: inset 3px 0 0 #18a058;
}

.phase-nav-index {
  display: inline-flex;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: rgb(255 255 255 / 8%);
  color: #f9fafb;
  font-size: 12px;
  font-weight: 800;
}

.phase-nav-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.phase-nav-main strong {
  overflow: hidden;
  color: #e5e7eb;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-nav-main em {
  color: #8b949e;
  font-size: 11px;
  font-style: normal;
}

.phase-nav-counts {
  grid-column: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.phase-nav-counts span {
  border-radius: 4px;
  background: rgb(255 255 255 / 6%);
  color: #9ca3af;
  font-size: 10px;
  padding: 2px 5px;
}

.phase-focus-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.phase-empty-state {
  display: flex;
  min-height: 280px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(0 0 0 / 10%);
  color: #9ca3af;
  text-align: center;
}

.phase-empty-state h3 {
  color: #e5e7eb;
  font-size: 15px;
  font-weight: 700;
}

.workspace-panel {
  flex: 1 1 auto;
}

.workspace-panel > :deep(.observer-lane-panel),
.workspace-panel > :deep(.assist-lane-panel) {
  flex: 1 1 auto;
  min-height: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.drawer-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.drawer-stack .cycle-side-fill {
  min-height: 260px;
}

.drawer-stack .cycle-side-log {
  min-height: 220px;
}

.cycle-drawer-handle {
  position: fixed;
  top: 50%;
  right: 0;
  z-index: 25;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 72px;
  padding: 0;
  border: 1px solid rgb(255 255 255 / 12%);
  border-right: 0;
  border-radius: 8px 0 0 8px;
  background: rgb(45 45 50 / 96%);
  color: rgb(229 231 235);
  font-size: 12px;
  line-height: 1;
  writing-mode: vertical-rl;
  transform: translateY(-50%);
  box-shadow: 0 8px 24px rgb(0 0 0 / 28%);
  cursor: pointer;
}

.cycle-drawer-handle:hover {
  background: rgb(64 64 70 / 98%);
}

.cycle-side-section {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.cycle-side-section:first-child {
  padding: 16px;
}

.cycle-side-fill,
.cycle-side-log {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cycle-side-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}

@media (max-width: 980px) {
  .cycle-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .phase-navigator {
    max-height: 280px;
  }

  .summary-role-list {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .cycle-workspace-tabs {
    grid-template-columns: minmax(0, 1fr);
  }

  .phase-focus-header {
    align-items: stretch;
    flex-direction: column;
  }

  .summary-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
