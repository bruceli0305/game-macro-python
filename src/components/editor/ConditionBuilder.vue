<script setup lang="ts">
import { NButton, NSelect, NInputNumber, NSpace, NPopconfirm } from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import type { Expr } from "../../types/ast";

const props = defineProps<{
  modelValue: Expr | null;
  skills: { id: string; name: string }[];
  points: { id: string; name: string }[];
}>();

const emit = defineEmits<{ "update:modelValue": [v: Expr | null] }>();

const expr = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

// 当前节点类型 → 子类型选项
const nodeTypes = [
  { label: "AND (全部满足)", value: "and" },
  { label: "OR (任一满足)", value: "or" },
  { label: "NOT (取反)", value: "not" },
  { label: "技能像素匹配", value: "pixel_skill" },
  { label: "点位像素匹配", value: "pixel_point" },
  { label: "技能计数达标", value: "skill_metric_ge" },
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
  props.skills.map((s) => ({ label: s.name || s.id, value: s.id }))
);
const pointOptions = computed(() =>
  props.points.map((p) => ({ label: p.name || p.id, value: p.id }))
);

function nodeType(e: Expr | null): string {
  if (!e) return "";
  if (e.type === "const") return e.value ? "const_true" : "const_false";
  return e.type;
}

function setType(typ: string) {
  if (!expr.value || nodeType(expr.value) !== typ) {
    switch (typ) {
      case "and": expr.value = { type: "and", children: [] }; break;
      case "or": expr.value = { type: "or", children: [] }; break;
      case "not": expr.value = { type: "not", child: { type: "const", value: true } }; break;
      case "pixel_skill": expr.value = { type: "pixel_skill", skill_id: "", tolerance: 20 }; break;
      case "pixel_point": expr.value = { type: "pixel_point", point_id: "", tolerance: 20 }; break;
      case "skill_metric_ge": expr.value = { type: "skill_metric_ge", skill_id: "", metric: "success", count: 1 }; break;
      case "const_true": expr.value = { type: "const", value: true }; break;
      case "const_false": expr.value = { type: "const", value: false }; break;
    }
  }
}

// And/Or children
function children(): Expr[] {
  if (!expr.value) return [];
  if (expr.value.type === "and" || expr.value.type === "or") return expr.value.children;
  return [];
}

function addChild() {
  const e = expr.value;
  if (e && (e.type === "and" || e.type === "or")) {
    e.children.push({ type: "const", value: true });
  }
}

function removeChild(i: number) {
  const e = expr.value;
  if (e && (e.type === "and" || e.type === "or")) {
    e.children.splice(i, 1);
  }
}

import { computed } from "vue";
</script>

<template>
  <div v-if="!expr" class="flex items-center gap-2">
    <span class="text-sm text-gray-400">无条件</span>
    <n-select
      :options="nodeTypes"
      size="tiny"
      placeholder="+ 添加条件"
      style="width:160px"
      @update:value="(v: string) => setType(v)"
    />
    <span class="text-xs text-gray-500">（始终就绪）</span>
  </div>
  <div v-else class="border border-white/10 rounded p-2 space-y-2">
    <!-- 节点类型选择 -->
    <n-select
      :value="nodeType(expr)"
      :options="nodeTypes"
      size="tiny"
      style="max-width:200px"
      @update:value="(v: string) => setType(v)"
    />

    <!-- AND/OR: 子节点列表 -->
    <template v-if="expr.type === 'and' || expr.type === 'or'">
      <div class="pl-3 border-l border-white/10 space-y-1">
        <template v-for="(child, i) in children()" :key="i">
          <div class="flex items-start gap-1">
            <div class="flex-1">
              <ConditionBuilder
                :model-value="child"
                :skills="skills"
                :points="points"
                @update:model-value="(v) => { if (v) children()[i] = v; }"
              />
            </div>
            <n-popconfirm @positive-click="removeChild(i)">
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

    <!-- NOT: 子节点 -->
    <template v-if="expr && expr.type === 'not'">
      <div class="pl-3 border-l border-white/10">
        <ConditionBuilder
          :model-value="expr.child"
          :skills="skills"
          :points="points"
          @update:model-value="(v: any) => { if (v && expr && expr.type === 'not') expr.child = v; }"
        />
      </div>
    </template>

    <!-- PixelMatchSkill -->
    <template v-if="expr.type === 'pixel_skill'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" style="max-width:200px" />
        <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" style="width:100px" placeholder="容差" />
      </n-space>
    </template>

    <!-- PixelMatchPoint -->
    <template v-if="expr.type === 'pixel_point'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.point_id" :options="pointOptions" size="tiny" placeholder="选择点位" style="max-width:200px" />
        <n-input-number v-model:value="expr.tolerance" :min="0" :max="255" size="tiny" style="width:100px" placeholder="容差" />
      </n-space>
    </template>

    <!-- SkillMetricGE -->
    <template v-if="expr.type === 'skill_metric_ge'">
      <n-space vertical size="small">
        <n-select v-model:value="expr.skill_id" :options="skillOptions" size="tiny" placeholder="选择技能" style="max-width:200px" />
        <n-select v-model:value="expr.metric" :options="metricOptions" size="tiny" style="max-width:150px" />
        <n-input-number v-model:value="expr.count" :min="1" :max="999" size="tiny" style="width:100px" placeholder="阈值" />
      </n-space>
    </template>
  </div>
</template>
