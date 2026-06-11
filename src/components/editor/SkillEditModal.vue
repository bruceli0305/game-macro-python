<script setup lang="ts">
import { reactive, watch, ref, onMounted } from "vue";
import {
  NModal, NCard, NButton, NSpace, NInput, NInputNumber, NSelect, NSwitch, NDivider,
} from "naive-ui";
import ConditionBuilder from "./ConditionBuilder.vue";
import PostActionsEditor from "./PostActionsEditor.vue";
import type { AttemptPolicy, SkillSlot, SkillSlotRole } from "../../types/cycle";
import type { Expr } from "../../types/ast";
import {
  buildCompleteDetectionExpr,
  buildStartDetectionExpr,
  DEFAULT_DETECTION_TOLERANCE,
  firstPointId,
  type CompleteDetectionTemplate,
  type StartDetectionTemplate,
} from "../../utils/detection-templates";

const props = defineProps<{
  show: boolean;
  slot: SkillSlot;
  skillOptions: { id: string; name: string }[];
  pointOptions: { id: string; name: string }[];
  markerOptions?: { id: string; name: string; allowed_values?: string[] }[];
  timerOptions?: { id: string; name: string }[];
  counterOptions?: { id: string; name: string }[];
}>();

const emit = defineEmits<{
  "update:show": [v: boolean];
  saved: [slot: SkillSlot];
}>();

const form = reactive<SkillSlot>({
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

const defaultAttemptPolicy = (): AttemptPolicy => ({
  max_attempts: 1,
  start_timeout_ms: 80,
  complete_timeout_ms: 0,
  retry_delay_ms: 30,
  failure_policy: "next_slot",
  complete_fallback: "assume_success_after_timeout",
});

const failurePolicyOptions = [
  { label: "失败后尝试下个技能", value: "next_slot" },
  { label: "失败后停留当前阶段", value: "hold_phase" },
  { label: "失败后进入下一阶段", value: "next_phase" },
];

const completeFallbackOptions = [
  { label: "完成超时后按成功处理", value: "assume_success_after_timeout" },
  { label: "完成超时后判定失败", value: "fail" },
];

const readinessPolicyOptions = [
  { label: "必须就绪才释放", value: "required" },
  { label: "仅记录信号，不阻断释放", value: "advisory" },
];

const slotRoleOptions: { label: string; value: SkillSlotRole }[] = [
  { label: "必放", value: "mandatory" },
  { label: "优先", value: "priority" },
  { label: "填充", value: "filler" },
];

type StartTemplateValue = StartDetectionTemplate | "custom";
type CompleteTemplateValue = CompleteDetectionTemplate | "custom";

const startDetectionTemplate = ref<StartTemplateValue>("custom");
const completeDetectionTemplate = ref<CompleteTemplateValue>("custom");
const startPointId = ref("");
const completePointId = ref("");
const startTolerance = ref(DEFAULT_DETECTION_TOLERANCE);
const completeTolerance = ref(DEFAULT_DETECTION_TOLERANCE);

const startDetectionOptions = [
  { label: "无开始检测", value: "none" },
  { label: "立即进入完成等待", value: "immediate" },
  { label: "状态条变化", value: "cast_bar_changed" },
  { label: "施法条 ROI 变化", value: "cast_bar_roi_changed" },
  { label: "Castbar Clarity 边框出现", value: "cast_bar_roi_border_visible" },
  { label: "高级条件", value: "custom" },
];

const completeDetectionOptions = [
  { label: "按读条/完成超时计时", value: "timer" },
  { label: "状态条变化", value: "cast_bar_changed" },
  { label: "施法条 ROI 消失", value: "cast_bar_roi_gone" },
  { label: "技能图标匹配", value: "skill_pixel" },
  { label: "技能图标变黑", value: "skill_pixel_black" },
  { label: "高级条件", value: "custom" },
];

function setAttemptPolicyEnabled(enabled: boolean) {
  form.attempt_policy = enabled ? (form.attempt_policy ?? defaultAttemptPolicy()) : null;
}

function assignStartExpr(expr: Expr | null) {
  form.start_expr = expr as Record<string, unknown> | null;
}

function assignCompleteExpr(expr: Expr | null) {
  form.complete_expr = expr as Record<string, unknown> | null;
}

function ensurePointDefaults() {
  const fallback = firstPointId(props.pointOptions);
  if (!startPointId.value) startPointId.value = fallback;
  if (!completePointId.value) completePointId.value = fallback;
}

function syncDetectionTemplateState() {
  ensurePointDefaults();

  const startExpr = form.start_expr as Expr | null;
  if (!startExpr) {
    startDetectionTemplate.value = "none";
  } else if (startExpr.type === "const" && startExpr.value) {
    startDetectionTemplate.value = "immediate";
  } else if (startExpr.type === "cast_bar_changed") {
    startDetectionTemplate.value = "cast_bar_changed";
    startPointId.value = startExpr.point_id;
    startTolerance.value = startExpr.tolerance;
  } else if (startExpr.type === "cast_bar_roi_changed") {
    startDetectionTemplate.value = "cast_bar_roi_changed";
  } else if (startExpr.type === "cast_bar_roi_border_visible") {
    startDetectionTemplate.value = "cast_bar_roi_border_visible";
  } else {
    startDetectionTemplate.value = "custom";
  }

  const completeExpr = form.complete_expr as Expr | null;
  if (!completeExpr) {
    completeDetectionTemplate.value = "timer";
  } else if (completeExpr.type === "cast_bar_changed") {
    completeDetectionTemplate.value = "cast_bar_changed";
    completePointId.value = completeExpr.point_id;
    completeTolerance.value = completeExpr.tolerance;
  } else if (completeExpr.type === "cast_bar_roi_gone") {
    completeDetectionTemplate.value = "cast_bar_roi_gone";
  } else if (completeExpr.type === "pixel_skill") {
    completeDetectionTemplate.value = "skill_pixel";
    completeTolerance.value = completeExpr.tolerance;
  } else if (completeExpr.type === "pixel_skill_black") {
    completeDetectionTemplate.value = "skill_pixel_black";
    completeTolerance.value = completeExpr.tolerance;
  } else {
    completeDetectionTemplate.value = "custom";
  }
}

function applyStartDetectionTemplate(value: StartTemplateValue) {
  startDetectionTemplate.value = value;
  if (value === "custom") return;
  ensurePointDefaults();
  assignStartExpr(buildStartDetectionExpr(value, startPointId.value, startTolerance.value));
}

function applyCompleteDetectionTemplate(value: CompleteTemplateValue) {
  completeDetectionTemplate.value = value;
  if (value === "custom") return;
  ensurePointDefaults();
  assignCompleteExpr(
    buildCompleteDetectionExpr(value, form.skill_id, completePointId.value, completeTolerance.value)
  );
}

function refreshStartCastBarExpr() {
  if (startDetectionTemplate.value !== "cast_bar_changed") return;
  assignStartExpr(buildStartDetectionExpr("cast_bar_changed", startPointId.value, startTolerance.value));
}

function refreshCompleteTemplateExpr() {
  if (completeDetectionTemplate.value === "custom") return;
  assignCompleteExpr(
    buildCompleteDetectionExpr(
      completeDetectionTemplate.value,
      form.skill_id,
      completePointId.value,
      completeTolerance.value
    )
  );
}

watch(() => props.show, (val) => {
  if (val) {
    Object.assign(form, {
      ...JSON.parse(JSON.stringify(props.slot)),
      slot_role: props.slot.slot_role ?? "mandatory",
      readiness_expr: props.slot.readiness_expr ?? null,
      readiness_policy: props.slot.readiness_policy ?? "required",
      protected_release: props.slot.protected_release ?? false,
      attempt_policy: props.slot.attempt_policy
        ? JSON.parse(JSON.stringify(props.slot.attempt_policy))
        : null,
      post_actions: props.slot.post_actions
        ? JSON.parse(JSON.stringify(props.slot.post_actions))
        : [],
    });
    syncDetectionTemplateState();
  }
});

// 从技能列表加载名称
const skillList = ref<{ id: string; name: string }[]>([]);
onMounted(() => {
  skillList.value = props.skillOptions;
  ensurePointDefaults();
});

function save() {
  emit("saved", JSON.parse(JSON.stringify(form)));
  emit("update:show", false);
}
</script>

<template>
  <n-modal :show="props.show" @update:show="(v: boolean) => emit('update:show', v)">
    <n-card title="编辑技能" style="width:500px; max-height:80vh; overflow-y:auto" closable @close="emit('update:show', false)">
      <n-space vertical size="small">
        <n-select
          v-model:value="form.skill_id"
          :options="skillList.map(s => ({ label: s.name || s.id, value: s.id }))"
          size="small"
          filterable
          placeholder="选择技能"
          @update:value="refreshCompleteTemplateExpr"
        />
        <n-input v-model:value="form.label" size="small" placeholder="显示标签（可选）" />
        <n-select
          v-model:value="form.slot_role"
          :options="slotRoleOptions"
          size="small"
          placeholder="技能槽类型"
        />
        <n-input-number v-model:value="form.priority" size="small" :min="1" :max="99" placeholder="决策顺位（数字越小越先）" />
        <n-input-number v-model:value="form.override_cast_ms" size="small" :min="0" placeholder="覆盖读条时间(ms)" />
        <div class="flex items-center justify-between rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div>
            <div class="text-sm text-gray-200">保护释放</div>
            <div class="text-xs text-gray-500">开启后，该技能等待释放完成期间禁止辅助 Lane 插入</div>
          </div>
          <n-switch v-model:value="form.protected_release" />
        </div>

        <div class="text-xs text-gray-400 pt-2">可释放条件（当前帧）</div>
        <ConditionBuilder
          :model-value="form.condition_expr as any"
          :skills="skillList"
          :points="pointOptions"
          :markers="markerOptions"
          :timers="timerOptions"
          :counters="counterOptions"
          @update:model-value="(v: any) => (form.condition_expr as any) = v"
        />
        <div class="text-xs text-gray-400 pt-2">就绪信号</div>
        <div class="rounded border border-white/10 bg-white/[0.03] p-2 space-y-2">
          <n-select
            v-model:value="form.readiness_policy"
            :options="readinessPolicyOptions"
            size="small"
            placeholder="就绪信号策略"
          />
          <div class="text-xs text-gray-500">
            硬条件决定当前帧是否进入候选列表；就绪信号用于识别图标、ROI 或其它弱状态。选择“仅记录信号”时，失败不会阻断按键尝试。
          </div>
        </div>
        <ConditionBuilder
          :model-value="form.readiness_expr as any"
          :skills="skillList"
          :points="pointOptions"
          :markers="markerOptions"
          :timers="timerOptions"
          :counters="counterOptions"
          @update:model-value="(v: any) => (form.readiness_expr as any) = v"
        />
        <div class="text-xs text-gray-400 pt-2">施法状态确认</div>
        <div class="rounded border border-white/10 bg-white/[0.03] p-2 space-y-2">
          <n-select
            :value="startDetectionTemplate"
            :options="startDetectionOptions"
            size="small"
            placeholder="选择释放开始模板"
            @update:value="(v: StartTemplateValue) => applyStartDetectionTemplate(v)"
          />
          <n-space v-if="startDetectionTemplate === 'cast_bar_changed'" size="small">
            <n-select
              v-model:value="startPointId"
              :options="pointOptions.map(p => ({ label: p.name || p.id, value: p.id }))"
              size="small"
              placeholder="状态条点位"
              style="min-width:180px"
              @update:value="refreshStartCastBarExpr"
            />
            <n-input-number
              v-model:value="startTolerance"
              :min="0"
              :max="255"
              size="small"
              placeholder="变化容差"
              @update:value="refreshStartCastBarExpr"
            />
          </n-space>
          <div class="text-xs text-gray-500">
            这里不是延迟排程；它只用于确认按键后是否真的进入施法/释放状态，未命中时由下方确认策略决定是否重试。
          </div>
        </div>
        <ConditionBuilder
          :model-value="form.start_expr as any"
          :skills="skillList"
          :points="pointOptions"
          :markers="markerOptions"
          :timers="timerOptions"
          :counters="counterOptions"
          @update:model-value="(v: any) => { (form.start_expr as any) = v; syncDetectionTemplateState(); }"
        />
        <div class="text-xs text-gray-400 pt-2">释放完成检测</div>
        <div class="rounded border border-white/10 bg-white/[0.03] p-2 space-y-2">
          <n-select
            :value="completeDetectionTemplate"
            :options="completeDetectionOptions"
            size="small"
            placeholder="选择释放完成模板"
            @update:value="(v: CompleteTemplateValue) => applyCompleteDetectionTemplate(v)"
          />
          <n-space v-if="completeDetectionTemplate === 'cast_bar_changed'" size="small">
            <n-select
              v-model:value="completePointId"
              :options="pointOptions.map(p => ({ label: p.name || p.id, value: p.id }))"
              size="small"
              placeholder="状态条点位"
              style="min-width:180px"
              @update:value="refreshCompleteTemplateExpr"
            />
            <n-input-number
              v-model:value="completeTolerance"
              :min="0"
              :max="255"
              size="small"
              placeholder="变化容差"
              @update:value="refreshCompleteTemplateExpr"
            />
          </n-space>
          <n-space v-if="completeDetectionTemplate === 'skill_pixel' || completeDetectionTemplate === 'skill_pixel_black'" size="small">
            <n-input-number
              v-model:value="completeTolerance"
              :min="0"
              :max="255"
              size="small"
              placeholder="技能图标容差"
              @update:value="refreshCompleteTemplateExpr"
            />
          </n-space>
          <div class="text-xs text-gray-500">
            按读条计时时不写完成条件，使用技能读条时间或槽位完成超时；状态条/图标模板会写入 AST 条件。
          </div>
        </div>
        <ConditionBuilder
          :model-value="form.complete_expr as any"
          :skills="skillList"
          :points="pointOptions"
          :markers="markerOptions"
          :timers="timerOptions"
          :counters="counterOptions"
          @update:model-value="(v: any) => { (form.complete_expr as any) = v; syncDetectionTemplateState(); }"
        />

        <PostActionsEditor
          :model-value="form.post_actions"
          :marker-options="markerOptions"
          :timer-options="timerOptions"
          :counter-options="counterOptions"
          @update:model-value="(value) => form.post_actions = value"
        />

        <n-divider class="!my-2">失败与重试</n-divider>
        <div class="flex items-center justify-between rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div>
            <div class="text-sm text-gray-200">槽位级确认策略</div>
            <div class="text-xs text-gray-500">关闭时使用基础配置中的全局状态机策略</div>
          </div>
          <n-switch :value="!!form.attempt_policy" @update:value="setAttemptPolicyEnabled" />
        </div>
        <template v-if="form.attempt_policy">
          <n-space vertical size="small">
            <n-input-number
              v-model:value="form.attempt_policy.max_attempts"
              size="small"
              :min="1"
              :max="21"
              placeholder="总尝试次数"
            >
              <template #prefix>总尝试</template>
            </n-input-number>
            <n-input-number
              v-model:value="form.attempt_policy.start_timeout_ms"
              size="small"
              :min="1"
              :max="600000"
              placeholder="施法确认窗口(ms)"
            >
              <template #prefix>确认窗口</template>
            </n-input-number>
            <n-input-number
              v-model:value="form.attempt_policy.complete_timeout_ms"
              size="small"
              :min="0"
              :max="600000"
              placeholder="释放完成超时(ms)，0 表示按全局读条等待"
            >
              <template #prefix>完成超时</template>
            </n-input-number>
            <n-input-number
              v-model:value="form.attempt_policy.retry_delay_ms"
              size="small"
              :min="0"
              :max="60000"
              placeholder="重试间隔(ms)"
            >
              <template #prefix>重试间隔</template>
            </n-input-number>
            <n-select
              v-model:value="form.attempt_policy.failure_policy"
              :options="failurePolicyOptions"
              size="small"
              placeholder="失败策略"
            />
            <n-select
              v-model:value="form.attempt_policy.complete_fallback"
              :options="completeFallbackOptions"
              size="small"
              placeholder="完成超时兜底"
            />
            <div class="rounded border border-emerald-400/20 bg-emerald-400/5 px-3 py-2 text-xs text-emerald-100/80">
              每次尝试只发送一次按键；如果确认窗口内没有检测到施法状态，会按策略重试或失败。
            </div>
          </n-space>
        </template>
      </n-space>

      <n-space justify="end" class="mt-4">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" @click="save">确定</n-button>
      </n-space>
    </n-card>
  </n-modal>
</template>
