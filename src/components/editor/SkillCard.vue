<script setup lang="ts">
import { computed } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";
import {
  IconChartBar,
  IconClock,
  IconEye,
  IconKeyboard,
  IconLink,
  IconMinus,
  IconPencil,
  IconTrash,
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
    class="skill-card flex h-[112px] w-56 flex-shrink-0 flex-col overflow-hidden rounded border border-white/10 bg-white/[0.04] transition-colors hover:bg-white/[0.08]"
    @dblclick="onDblClick"
  >
    <div class="skill-card-header flex items-center gap-1.5 px-2 py-1.5 border-b border-white/5">
      <span
        class="skill-card-index inline-flex items-center justify-center min-w-[20px] h-5 rounded-full text-[11px] font-bold text-white flex-shrink-0"
        :style="{ backgroundColor: conditionMeta.color }"
      >
        {{ index + 1 }}
      </span>
      <span class="skill-card-title text-xs text-gray-200 font-medium truncate flex-1 min-w-0">
        {{ skillName || slot.skill_id || "未选择" }}
      </span>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click.stop="emit('edit')">
            <template #icon><IconPencil :size="13" /></template>
          </n-button>
        </template>
        编辑技能槽
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle type="error" @click.stop="emit('remove')">
            <template #icon><IconTrash :size="13" /></template>
          </n-button>
        </template>
        删除技能槽
      </n-tooltip>
    </div>

    <div class="skill-card-body min-h-0 flex-1 px-2 py-1 text-[11px] text-gray-400 space-y-0.5">
      <div class="skill-card-row flex items-center gap-1 min-w-0">
        <NIcon size="13"><IconKeyboard /></NIcon>
        <span class="truncate">{{ triggerKey }}</span>
      </div>
      <div class="skill-card-row flex items-center gap-1 min-w-0">
        <NIcon size="13"><IconClock /></NIcon>
        <span class="truncate">{{ timingLabel }}</span>
      </div>
    </div>

    <n-tooltip trigger="hover">
      <template #trigger>
        <div
          class="skill-card-condition flex items-center gap-1 px-2 py-1 text-[11px] border-t border-white/5 cursor-help"
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

<style scoped>
.skill-card {
  display: flex;
  flex: 0 0 224px;
  flex-direction: column;
  width: 224px;
  height: 112px;
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 4%);
  transition: background-color 0.15s ease;
}

.skill-card:hover {
  background: rgb(255 255 255 / 8%);
}

.skill-card-header,
.skill-card-row,
.skill-card-condition {
  display: flex;
  align-items: center;
}

.skill-card-header {
  gap: 6px;
  border-bottom: 1px solid rgb(255 255 255 / 5%);
  padding: 6px 8px;
}

.skill-card-index {
  display: inline-flex;
  flex: 0 0 auto;
  min-width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.skill-card-title,
.skill-card-row span,
.skill-card-condition span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-card-title {
  flex: 1 1 auto;
  color: #e5e7eb;
  font-size: 12px;
  font-weight: 500;
}

.skill-card-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 4px 8px;
  color: #9ca3af;
  font-size: 11px;
}

.skill-card-row {
  min-width: 0;
  gap: 4px;
  line-height: 18px;
}

.skill-card-condition {
  gap: 4px;
  border-top: 1px solid rgb(255 255 255 / 5%);
  padding: 4px 8px;
  font-size: 11px;
}
</style>
