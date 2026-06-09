<script setup lang="ts">
import { computed } from "vue";
import { NButton, NInput, NInputNumber, NPopconfirm, NSelect, NSpace } from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import type { Expr } from "../../types/ast";

const props = defineProps<{
  modelValue: Expr | null;
  skills: { id: string; name: string }[];
  points: { id: string; name: string }[];
  markers?: { id: string; name: string; allowed_values?: string[] }[];
  timers?: { id: string; name: string }[];
  counters?: { id: string; name: string }[];
}>();

const emit = defineEmits<{ "update:modelValue": [value: Expr | null] }>();

const expr = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const nodeTypes = [
  { label: "AND（全部满足）", value: "and" },
  { label: "OR（任一满足）", value: "or" },
  { label: "NOT（取反）", value: "not" },
  { label: "技能像素匹配", value: "pixel_skill" },
  { label: "技能像素不匹配", value: "pixel_skill_not_match" },
  { label: "技能像素为黑", value: "pixel_skill_black" },
  { label: "技能像素非黑", value: "pixel_skill_not_black" },
  { label: "点位像素匹配", value: "pixel_point" },
  { label: "点位像素不匹配", value: "pixel_point_not_match" },
  { label: "点位为黑", value: "pixel_point_black" },
  { label: "点位非黑", value: "pixel_point_not_black" },
  { label: "状态条变化", value: "cast_bar_changed" },
  { label: "施法条 ROI 变化", value: "cast_bar_roi_changed" },
  { label: "施法条 ROI 边框出现", value: "cast_bar_roi_border_visible" },
  { label: "施法条 ROI 消失", value: "cast_bar_roi_gone" },
  { label: "技能指标达到", value: "skill_metric_ge" },
  { label: "标记等于", value: "marker_eq" },
  { label: "标记不等于", value: "marker_ne" },
  { label: "时间标记已超过", value: "timer_elapsed_ge" },
  { label: "时间标记未超过", value: "timer_elapsed_lt" },
  { label: "计数器大于等于", value: "counter_ge" },
  { label: "计数器等于", value: "counter_eq" },
  { label: "计数器大于", value: "counter_gt" },
  { label: "恒真", value: "const_true" },
  { label: "恒假", value: "const_false" },
];

const metricOptions = [
  { label: "成功次数", value: "success" },
  { label: "尝试次数", value: "attempt_started" },
  { label: "发键成功", value: "key_sent_ok" },
  { label: "施法开始", value: "cast_started" },
  { label: "失败次数", value: "fail" },
];

const skillOptions = computed(() =>
  props.skills.map((skill) => ({ label: skill.name || skill.id, value: skill.id }))
);
const pointOptions = computed(() =>
  props.points.map((point) => ({ label: point.name || point.id, value: point.id }))
);
const markerOptions = computed(() =>
  (props.markers ?? []).map((marker) => ({ label: marker.name || marker.id, value: marker.id }))
);
const timerOptions = computed(() =>
  (props.timers ?? []).map((timer) => ({ label: timer.name || timer.id, value: timer.id }))
);
const counterOptions = computed(() =>
  (props.counters ?? []).map((counter) => ({ label: counter.name || counter.id, value: counter.id }))
);
const markerValueOptions = computed(() => {
  const current = expr.value;
  if (!current || (current.type !== "marker_eq" && current.type !== "marker_ne")) return [];
  const marker = (props.markers ?? []).find((item) => item.id === current.marker_id);
  return (marker?.allowed_values ?? []).map((value) => ({ label: value, value }));
});

function nodeType(value: Expr | null): string {
  if (!value) return "";
  if (value.type === "const") return value.value ? "const_true" : "const_false";
  return value.type;
}

function setType(type: string) {
  if (expr.value && nodeType(expr.value) === type) return;
  switch (type) {
    case "and":
      expr.value = { type: "and", children: [] };
      break;
    case "or":
      expr.value = { type: "or", children: [] };
      break;
    case "not":
      expr.value = { type: "not", child: { type: "const", value: true } };
      break;
    case "pixel_skill":
      expr.value = { type: "pixel_skill", skill_id: "", tolerance: 20 };
      break;
    case "pixel_skill_not_match":
      expr.value = { type: "pixel_skill_not_match", skill_id: "", tolerance: 20 };
      break;
    case "pixel_skill_black":
      expr.value = { type: "pixel_skill_black", skill_id: "", tolerance: 5 };
      break;
    case "pixel_skill_not_black":
      expr.value = { type: "pixel_skill_not_black", skill_id: "", tolerance: 5 };
      break;
    case "pixel_point":
      expr.value = { type: "pixel_point", point_id: "", tolerance: 20 };
      break;
    case "pixel_point_not_match":
      expr.value = { type: "pixel_point_not_match", point_id: "", tolerance: 20 };
      break;
    case "pixel_point_black":
      expr.value = { type: "pixel_point_black", point_id: "", tolerance: 5 };
      break;
    case "pixel_point_not_black":
      expr.value = { type: "pixel_point_not_black", point_id: "", tolerance: 5 };
      break;
    case "cast_bar_changed":
      expr.value = { type: "cast_bar_changed", point_id: "", tolerance: 20 };
      break;
    case "cast_bar_roi_changed":
      expr.value = { type: "cast_bar_roi_changed" };
      break;
    case "cast_bar_roi_border_visible":
      expr.value = { type: "cast_bar_roi_border_visible" };
      break;
    case "cast_bar_roi_gone":
      expr.value = { type: "cast_bar_roi_gone" };
      break;
    case "skill_metric_ge":
      expr.value = { type: "skill_metric_ge", skill_id: "", metric: "success", count: 1 };
      break;
    case "marker_eq":
      expr.value = { type: "marker_eq", marker_id: "", value: "" };
      break;
    case "marker_ne":
      expr.value = { type: "marker_ne", marker_id: "", value: "" };
      break;
    case "timer_elapsed_ge":
      expr.value = { type: "timer_elapsed_ge", timer_id: "", ms: 1000 };
      break;
    case "timer_elapsed_lt":
      expr.value = { type: "timer_elapsed_lt", timer_id: "", ms: 1000 };
      break;
    case "counter_ge":
      expr.value = { type: "counter_ge", counter_id: "", value: 1 };
      break;
    case "counter_eq":
      expr.value = { type: "counter_eq", counter_id: "", value: 0 };
      break;
    case "counter_gt":
      expr.value = { type: "counter_gt", counter_id: "", value: 0 };
      break;
    case "const_true":
      expr.value = { type: "const", value: true };
      break;
    case "const_false":
      expr.value = { type: "const", value: false };
      break;
  }
}

function children(): Expr[] {
  const current = expr.value;
  if (current?.type === "and" || current?.type === "or") return current.children;
  return [];
}

function addChild() {
  const current = expr.value;
  if (current?.type === "and" || current?.type === "or") {
    current.children.push({ type: "const", value: true });
  }
}

function removeChild(index: number) {
  const current = expr.value;
  if (current?.type === "and" || current?.type === "or") {
    current.children.splice(index, 1);
  }
}

function updateNotChild(value: Expr | null) {
  const current = expr.value;
  if (value && current?.type === "not") {
    current.child = value;
  }
}

function isSkillPixelExpr(value: Expr | null): value is Extract<
  Expr,
  { type: "pixel_skill" | "pixel_skill_not_match" | "pixel_skill_black" | "pixel_skill_not_black" }
> {
  return !!value && (
    value.type === "pixel_skill"
    || value.type === "pixel_skill_not_match"
    || value.type === "pixel_skill_black"
    || value.type === "pixel_skill_not_black"
  );
}

function isPointPixelExpr(value: Expr | null): value is Extract<
  Expr,
  { type: "pixel_point" | "pixel_point_not_match" | "pixel_point_black" | "pixel_point_not_black" }
> {
  return !!value && (
    value.type === "pixel_point"
    || value.type === "pixel_point_not_match"
    || value.type === "pixel_point_black"
    || value.type === "pixel_point_not_black"
  );
}
</script>

<template>
  <div v-if="!expr" class="flex items-center gap-2">
    <span class="text-sm text-gray-400">无条件</span>
    <n-select
      :options="nodeTypes"
      size="tiny"
      placeholder="+ 添加条件"
      style="width: 160px"
      @update:value="(value: string) => setType(value)"
    />
    <span class="text-xs text-gray-500">（始终就绪）</span>
  </div>

  <div v-else class="space-y-2 rounded border border-white/10 p-2">
    <n-select
      :value="nodeType(expr)"
      :options="nodeTypes"
      size="tiny"
      style="max-width: 200px"
      @update:value="(value: string) => setType(value)"
    />

    <template v-if="expr.type === 'and' || expr.type === 'or'">
      <div class="space-y-1 border-l border-white/10 pl-3">
        <template v-for="(child, index) in children()" :key="index">
          <div class="flex items-start gap-1">
            <div class="flex-1">
              <ConditionBuilder
                :model-value="child"
                :skills="skills"
                :points="points"
                :markers="markers"
                :timers="timers"
                :counters="counters"
                @update:model-value="(value) => { if (value) children()[index] = value; }"
              />
            </div>
            <n-popconfirm @positive-click="removeChild(index)">
              <template #trigger>
                <n-button size="tiny" quaternary type="error">
                  <template #icon><IconTrash /></template>
                </n-button>
              </template>
              删除此条件？
            </n-popconfirm>
          </div>
        </template>
      </div>
      <n-button size="tiny" dashed @click="addChild">
        <template #icon><IconPlus /></template>
        添加条件
      </n-button>
    </template>

    <template v-if="expr.type === 'not'">
      <div class="border-l border-white/10 pl-3">
        <ConditionBuilder
          :model-value="expr.child"
          :skills="skills"
          :points="points"
          :markers="markers"
          :timers="timers"
          :counters="counters"
          @update:model-value="updateNotChild"
        />
      </div>
    </template>

    <template v-if="isSkillPixelExpr(expr)">
      <n-space vertical size="small">
        <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" style="max-width: 200px" />
        <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" style="width: 120px" placeholder="容差/黑阈值" />
      </n-space>
    </template>

    <template v-if="isPointPixelExpr(expr)">
      <n-space vertical size="small">
        <n-select v-model:value="expr.point_id" :options="pointOptions" size="tiny" placeholder="选择点位" style="max-width: 200px" />
        <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" style="width: 120px" placeholder="容差/黑阈值" />
      </n-space>
    </template>

    <template v-if="expr.type === 'cast_bar_changed'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.point_id" :options="pointOptions" size="tiny" placeholder="选择状态条点位" style="max-width: 200px" />
        <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" style="width: 100px" placeholder="变化容差" />
      </n-space>
    </template>

    <template v-if="expr.type === 'cast_bar_roi_changed' || expr.type === 'cast_bar_roi_border_visible' || expr.type === 'cast_bar_roi_gone'">
      <div class="text-xs text-gray-500">
        使用基础配置中的施法条 ROI 区域、阈值和确认帧数。
      </div>
    </template>

    <template v-if="expr.type === 'skill_metric_ge'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" style="max-width: 200px" />
        <n-select v-model:value="expr.metric" :options="metricOptions" size="tiny" style="max-width: 150px" />
        <n-input-number v-model:value="expr.count" :min="1" :max="999" size="tiny" style="width: 100px" placeholder="阈值" />
      </n-space>
    </template>

    <template v-if="expr.type === 'marker_eq' || expr.type === 'marker_ne'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.marker_id" :options="markerOptions" size="tiny" placeholder="选择标记" style="max-width: 200px" />
        <n-select
          v-if="markerValueOptions.length > 0"
          v-model:value="expr.value"
          :options="markerValueOptions"
          size="tiny"
          placeholder="选择值"
          style="max-width: 160px"
        />
        <n-input v-else v-model:value="expr.value" size="tiny" placeholder="标记值" style="max-width: 160px" />
      </n-space>
    </template>

    <template v-if="expr.type === 'timer_elapsed_ge' || expr.type === 'timer_elapsed_lt'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.timer_id" :options="timerOptions" size="tiny" placeholder="选择时间标记" style="max-width: 200px" />
        <n-input-number v-model:value="expr.ms" :min="0" :max="600000" size="tiny" style="width: 120px" placeholder="毫秒" />
      </n-space>
    </template>

    <template v-if="expr.type === 'counter_ge' || expr.type === 'counter_eq' || expr.type === 'counter_gt'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.counter_id" :options="counterOptions" size="tiny" placeholder="选择计数器" style="max-width: 200px" />
        <n-input-number v-model:value="expr.value" :min="-999999" :max="999999" size="tiny" style="width: 120px" placeholder="阈值" />
      </n-space>
    </template>
  </div>
</template>
