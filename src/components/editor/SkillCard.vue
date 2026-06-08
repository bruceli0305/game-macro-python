<script setup lang="ts">
import { computed } from "vue";
import { NIcon, NTooltip } from "naive-ui";
import {
  IconChartBar,
  IconClock,
  IconEye,
  IconKeyboard,
  IconLink,
  IconMinus,
} from "@tabler/icons-vue";
import type { SkillSlot } from "../../types/cycle";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

const props = defineProps<{
  slot: SkillSlot;
  index: number;
  skillName: string | null;
  meta: SkillCardMeta | null;
}>();

const emit = defineEmits<{
  edit: [];
  remove: [];
}>();

const condition = computed(() => props.slot.condition_expr as any);

const conditionMeta = computed(() => {
  const expr = condition.value;
  if (!expr || !expr.type) {
    return { icon: IconMinus, color: "gray", label: "无条件" };
  }
  switch (expr.type) {
    case "pixel_skill":
    case "pixel_point":
    case "cast_bar_changed":
      return { icon: IconEye, color: "#2080f0", label: "像素匹配" };
    case "skill_metric_ge":
      return { icon: IconChartBar, color: "#18a058", label: "计数条件" };
    case "and":
    case "or":
    case "not":
      return { icon: IconLink, color: "#f0a020", label: "组合条件" };
    default:
      return { icon: IconMinus, color: "gray", label: "无条件" };
  }
});

const conditionSummary = computed(() => {
  const expr = condition.value;
  if (!expr || !expr.type) return "无条件";
  switch (expr.type) {
    case "pixel_skill":
      return `技能像素 ${expr.skill_id} tol=${expr.tolerance}`;
    case "pixel_point":
      return `点位像素 ${expr.point_id} tol=${expr.tolerance}`;
    case "skill_metric_ge":
      return `${expr.metric} >= ${expr.count}`;
    case "and":
      return `AND(${expr.children?.length || 0})`;
    case "or":
      return `OR(${expr.children?.length || 0})`;
    case "not":
      return "NOT";
    default:
      return "无条件";
  }
});

const triggerKey = computed(() => props.meta?.triggerKey || "-");
const timingLabel = computed(() => {
  if (!props.meta) return "未配置";
  const parts = [`读条 ${props.meta.readbarMs}ms`];
  if (props.meta.cooldownMs > 0) parts.push(`冷却 ${props.meta.cooldownMs}ms`);
  if (props.meta.shotsPerCycle > 1) parts.push(`每轮 ${props.meta.shotsPerCycle} 次`);
  return parts.join(" / ");
});

function onDblClick() {
  emit("edit");
}
</script>

<template>
  <div
    class="flex-shrink-0 w-44 rounded border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] cursor-pointer transition-colors overflow-hidden select-none"
    @dblclick="onDblClick"
  >
    <div class="flex items-center gap-1.5 px-2 py-1.5 border-b border-white/5">
      <span
        class="inline-flex items-center justify-center min-w-[20px] h-5 rounded-full text-[11px] font-bold text-white flex-shrink-0"
        :style="{ backgroundColor: conditionMeta.color }"
      >
        {{ index + 1 }}
      </span>
      <span class="text-xs text-gray-200 font-medium truncate flex-1 min-w-0">
        {{ skillName || slot.skill_id || "未选择" }}
      </span>
    </div>

    <div class="px-2 py-1 text-[11px] text-gray-400 space-y-0.5">
      <div class="flex items-center gap-1 min-w-0">
        <NIcon size="13"><IconKeyboard /></NIcon>
        <span class="truncate">{{ triggerKey }}</span>
      </div>
      <div class="flex items-center gap-1 min-w-0">
        <NIcon size="13"><IconClock /></NIcon>
        <span class="truncate">{{ timingLabel }}</span>
      </div>
    </div>

    <n-tooltip trigger="hover">
      <template #trigger>
        <div
          class="flex items-center gap-1 px-2 py-1 text-[11px] border-t border-white/5 cursor-help"
          :style="{ color: conditionMeta.color }"
        >
          <NIcon size="13" class="flex-shrink-0">
            <component :is="conditionMeta.icon" />
          </NIcon>
          <span class="truncate text-[10px] opacity-80">{{ conditionMeta.label }}</span>
        </div>
      </template>
      <span class="text-xs">{{ conditionSummary }}</span>
    </n-tooltip>
  </div>
</template>
