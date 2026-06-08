<script setup lang="ts">
import { computed } from "vue";
import { NTooltip } from "naive-ui";
import type { SkillSlot } from "../../types/cycle";

const props = defineProps<{
  slot: SkillSlot;
  index: number;
  skillName: string | null;
}>();

const emit = defineEmits<{
  edit: [];
  remove: [];
}>();

// 条件类型图标
const condIcon = computed(() => {
  const e = props.slot.condition_expr as any;
  if (!e || !e.type) return { icon: "—", color: "gray", label: "无条件" };
  switch (e.type) {
    case "pixel_skill":
    case "pixel_point":
    case "cast_bar_changed":
      return { icon: "👁", color: "#2080f0", label: "像素匹配" };
    case "skill_metric_ge":
      return { icon: "📊", color: "#18a058", label: "计数条件" };
    case "and":
    case "or":
    case "not":
      return { icon: "🔗", color: "#f0a020", label: "组合条件" };
    default:
      return { icon: "—", color: "gray", label: "无条件" };
  }
});

// 条件摘要
const condSummary = computed(() => {
  const e = props.slot.condition_expr as any;
  if (!e || !e.type) return "";
  switch (e.type) {
    case "pixel_skill": return `技能像素 ${e.skill_id} tol=${e.tolerance}`;
    case "pixel_point": return `点位像素 ${e.point_id} tol=${e.tolerance}`;
    case "skill_metric_ge": return `${e.metric} >= ${e.count}`;
    case "and": return `AND(${e.children?.length || 0})`;
    case "or": return `OR(${e.children?.length || 0})`;
    case "not": return `NOT`;
    default: return "";
  }
});

function onDblClick() { emit("edit"); }
</script>

<template>
  <div
    class="flex-shrink-0 w-40 rounded border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] cursor-pointer transition-colors overflow-hidden select-none"
    @dblclick="onDblClick"
  >
    <!-- 顶部：优先级 + 技能名 -->
    <div class="flex items-center gap-1.5 px-2 py-1.5 border-b border-white/5">
      <span
        class="inline-flex items-center justify-center min-w-[20px] h-5 rounded-full text-[11px] font-bold text-white flex-shrink-0"
        :style="{ backgroundColor: condIcon.color }"
      >
        {{ index + 1 }}
      </span>
      <span class="text-xs text-gray-200 font-medium truncate flex-1 min-w-0">
        {{ skillName || slot.skill_id || "未选择" }}
      </span>
    </div>

    <!-- 中部：触发键 -->
    <div class="px-2 py-0.5 text-[11px] text-gray-400">
      🔑 {{ slot.skill_id || "—" }}
    </div>

    <!-- 底部：条件图标 + 类型 -->
    <n-tooltip trigger="hover">
      <template #trigger>
        <div
          class="flex items-center gap-1 px-2 py-1 text-[11px] border-t border-white/5 cursor-help"
          :style="{ color: condIcon.color }"
        >
          <span class="flex-shrink-0">{{ condIcon.icon }}</span>
          <span class="truncate text-[10px] opacity-80">{{ condIcon.label }}</span>
        </div>
      </template>
      <span class="text-xs">{{ condSummary }}</span>
    </n-tooltip>
  </div>
</template>
