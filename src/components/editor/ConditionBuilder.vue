<script setup lang="ts">
import { computed } from "vue";
import { NButton, NInput, NInputNumber, NPopconfirm, NSelect } from "naive-ui";
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
  { label: "技能图标为黑", value: "pixel_skill_black" },
  { label: "技能图标非黑", value: "pixel_skill_not_black" },
  { label: "点位像素匹配", value: "pixel_point" },
  { label: "点位像素不匹配", value: "pixel_point_not_match" },
  { label: "点位为黑", value: "pixel_point_black" },
  { label: "点位非黑", value: "pixel_point_not_black" },
  { label: "点位最近颜色", value: "pixel_point_nearest" },
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
    case "pixel_point_nearest":
      expr.value = {
        type: "pixel_point_nearest",
        expected_point_id: "",
        candidate_point_ids: [],
        max_delta: 96,
        min_margin: 20,
      };
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

function isPointNearestExpr(value: Expr | null): value is Extract<
  Expr,
  { type: "pixel_point_nearest" }
> {
  return value?.type === "pixel_point_nearest";
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
  <div v-if="!expr" class="condition-empty">
    <span class="text-sm text-gray-400">无条件</span>
    <n-select
      :options="nodeTypes"
      size="tiny"
      placeholder="+ 添加条件"
      class="condition-type-select"
      @update:value="(value: string) => setType(value)"
    />
    <span class="text-xs text-gray-500">未设置时始终满足</span>
  </div>

  <div v-else class="condition-node">
    <div class="condition-node-toolbar">
      <n-select
        :value="nodeType(expr)"
        :options="nodeTypes"
        size="tiny"
        class="condition-type-select"
        @update:value="(value: string) => setType(value)"
      />
    </div>

    <template v-if="expr.type === 'and' || expr.type === 'or'">
      <div class="condition-children">
        <template v-for="(child, index) in children()" :key="index">
          <div class="condition-child-row">
            <ConditionBuilder
              class="condition-child-builder"
              :model-value="child"
              :skills="skills"
              :points="points"
              :markers="markers"
              :timers="timers"
              :counters="counters"
              @update:model-value="(value) => { if (value) children()[index] = value; }"
            />
            <n-popconfirm @positive-click="removeChild(index)">
              <template #trigger>
                <n-button size="tiny" quaternary type="error" class="condition-delete-button">
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
      <div class="condition-children">
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
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>技能</span>
          <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" />
        </label>
        <label class="condition-field short-field">
          <span>容差 / 黑阈值</span>
          <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" placeholder="20" />
        </label>
      </div>
    </template>

    <template v-if="isPointPixelExpr(expr)">
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>点位</span>
          <n-select v-model:value="expr.point_id" :options="pointOptions" size="tiny" placeholder="选择点位" />
        </label>
        <label class="condition-field short-field">
          <span>容差 / 黑阈值</span>
          <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" placeholder="20" />
        </label>
      </div>
    </template>

    <template v-if="isPointNearestExpr(expr)">
      <div class="condition-fields nearest-grid">
        <label class="condition-field">
          <span>目标点位</span>
          <n-select
            v-model:value="expr.expected_point_id"
            :options="pointOptions"
            size="tiny"
            placeholder="选择目标点位"
          />
        </label>
        <label class="condition-field candidate-field">
          <span>候选点位</span>
          <n-select
            v-model:value="expr.candidate_point_ids"
            :options="pointOptions"
            multiple
            size="tiny"
            placeholder="选择用于比较的候选点位"
          />
        </label>
        <label class="condition-field short-field">
          <span>最大差值</span>
          <n-input-number v-model:value="expr.max_delta" :min="0" :max="255" size="tiny" placeholder="96" />
        </label>
        <label class="condition-field short-field">
          <span>最小间隔</span>
          <n-input-number v-model:value="expr.min_margin" :min="0" :max="255" size="tiny" placeholder="20" />
        </label>
      </div>
    </template>

    <template v-if="expr.type === 'cast_bar_changed'">
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>状态条点位</span>
          <n-select v-model:value="expr.point_id" :options="pointOptions" size="tiny" placeholder="选择状态条点位" />
        </label>
        <label class="condition-field short-field">
          <span>变化容差</span>
          <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" placeholder="20" />
        </label>
      </div>
    </template>

    <template v-if="expr.type === 'cast_bar_roi_changed' || expr.type === 'cast_bar_roi_border_visible' || expr.type === 'cast_bar_roi_gone'">
      <div class="condition-note">
        使用基础配置中的施法条 ROI 区域、阈值和确认帧数。
      </div>
    </template>

    <template v-if="expr.type === 'skill_metric_ge'">
      <div class="condition-fields metric-grid">
        <label class="condition-field">
          <span>技能</span>
          <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" />
        </label>
        <label class="condition-field">
          <span>指标</span>
          <n-select v-model:value="expr.metric" :options="metricOptions" size="tiny" />
        </label>
        <label class="condition-field short-field">
          <span>阈值</span>
          <n-input-number v-model:value="expr.count" :min="1" :max="999" size="tiny" placeholder="1" />
        </label>
      </div>
    </template>

    <template v-if="expr.type === 'marker_eq' || expr.type === 'marker_ne'">
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>标记</span>
          <n-select v-model:value="expr.marker_id" :options="markerOptions" size="tiny" placeholder="选择标记" />
        </label>
        <label class="condition-field">
          <span>值</span>
          <n-select
            v-if="markerValueOptions.length > 0"
            v-model:value="expr.value"
            :options="markerValueOptions"
            size="tiny"
            placeholder="选择值"
          />
          <n-input v-else v-model:value="expr.value" size="tiny" placeholder="标记值" />
        </label>
      </div>
    </template>

    <template v-if="expr.type === 'timer_elapsed_ge' || expr.type === 'timer_elapsed_lt'">
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>时间标记</span>
          <n-select v-model:value="expr.timer_id" :options="timerOptions" size="tiny" placeholder="选择时间标记" />
        </label>
        <label class="condition-field short-field">
          <span>毫秒</span>
          <n-input-number v-model:value="expr.ms" :min="0" :max="600000" size="tiny" placeholder="1000" />
        </label>
      </div>
    </template>

    <template v-if="expr.type === 'counter_ge' || expr.type === 'counter_eq' || expr.type === 'counter_gt'">
      <div class="condition-fields two-cols">
        <label class="condition-field">
          <span>计数器</span>
          <n-select v-model:value="expr.counter_id" :options="counterOptions" size="tiny" placeholder="选择计数器" />
        </label>
        <label class="condition-field short-field">
          <span>阈值</span>
          <n-input-number v-model:value="expr.value" :min="-999999" :max="999999" size="tiny" placeholder="0" />
        </label>
      </div>
    </template>
  </div>
</template>

<style scoped>
.condition-empty {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.condition-node {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  padding: 10px;
}

.condition-node-toolbar {
  display: flex;
  min-width: 0;
  align-items: center;
}

.condition-type-select {
  width: min(260px, 100%);
}

.condition-children {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  border-left: 1px solid rgb(255 255 255 / 10%);
  padding-left: 10px;
}

.condition-child-row {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr) 28px;
  gap: 8px;
  align-items: start;
}

.condition-child-builder {
  min-width: 0;
}

.condition-delete-button {
  width: 28px;
}

.condition-fields {
  display: grid;
  min-width: 0;
  gap: 8px;
  align-items: end;
}

.two-cols {
  grid-template-columns: minmax(220px, 1fr) minmax(120px, 180px);
}

.nearest-grid {
  grid-template-columns: minmax(180px, 240px) minmax(260px, 1fr) minmax(108px, 128px) minmax(108px, 128px);
}

.metric-grid {
  grid-template-columns: minmax(220px, 1fr) minmax(140px, 180px) minmax(108px, 128px);
}

.condition-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  color: #9ca3af;
  font-size: 11px;
}

.condition-field :deep(.n-select),
.condition-field :deep(.n-input),
.condition-field :deep(.n-input-number) {
  width: 100%;
}

.short-field {
  min-width: 108px;
}

.candidate-field :deep(.n-base-selection-tags) {
  align-items: flex-start;
}

.condition-note {
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 4px;
  background: rgb(255 255 255 / 3%);
  padding: 8px 10px;
  color: #9ca3af;
  font-size: 12px;
}

@media (max-width: 900px) {
  .two-cols,
  .nearest-grid,
  .metric-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
