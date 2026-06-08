<script setup lang="ts">
import { NButton, NInput, NSelect, NPopconfirm } from "naive-ui";
import { IconPlus, IconTrash, IconChevronDown, IconChevronRight } from "@tabler/icons-vue";
import SkillCard from "./SkillCard.vue";
import type { CyclePhase } from "../../types/cycle";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

defineProps<{
  phase: CyclePhase;
  phaseIndex: number;
  skillNames: Record<string, string>;
  skillMeta: Record<string, SkillCardMeta>;
  collapsed: boolean;
}>();

const emit = defineEmits<{
  "update:phase": [phase: CyclePhase];
  remove: [];
  addSlot: [];
  editSlot: [index: number];
  removeSlot: [index: number];
  toggleCollapse: [];
}>();

const completeOptions = [
  { label: "全部释放后进入下一阶段", value: "all_fired" },
  { label: "任一释放后进入下一阶段", value: "any_fired" },
  { label: "都未就绪后进入下一阶段", value: "none_ready" },
  { label: "每次执行后立刻进入下一阶段", value: "always" },
];

function completeLabel(v: string) {
  const opt = completeOptions.find((o) => o.value === v);
  return opt ? opt.label.split(" ")[0] : v;
}
</script>

<template>
  <div class="phase-lane rounded border border-white/10 bg-[#121318] overflow-hidden">
    <!-- Phase 头部 -->
    <div class="phase-header grid grid-cols-[auto_auto_minmax(160px,220px)_minmax(220px,320px)_1fr_auto] items-center gap-2 border-b border-white/10 bg-white/[0.04] px-3 py-2">
      <n-button size="small" quaternary class="h-8 w-8" @click="emit('toggleCollapse')">
        <template #icon>
          <IconChevronDown v-if="!collapsed" :size="16" />
          <IconChevronRight v-else :size="16" />
        </template>
      </n-button>
      <span class="text-sm font-bold text-gray-200 whitespace-nowrap">P{{ phaseIndex + 1 }}</span>
      <n-input
        :value="phase.name"
        size="small"
        placeholder="阶段名称"
        @update:value="(v: string) => { phase.name = v; emit('update:phase', phase); }"
      />
      <n-select
        :value="phase.complete_when"
        :options="completeOptions"
        size="small"
        @update:value="(v: string) => { phase.complete_when = v as any; emit('update:phase', phase); }"
      />
      <div class="phase-header-spacer flex-1 min-w-[20px]" />
      <n-popconfirm @positive-click="emit('remove')">
        <template #trigger>
          <n-button size="small" quaternary type="error" class="h-8 w-8">
            <template #icon><IconTrash :size="16" /></template>
          </n-button>
        </template>
        删除？
      </n-popconfirm>
    </div>

    <!-- 卡片区域（可折叠） -->
    <div v-if="!collapsed" class="phase-body px-3 py-3">
      <div
        v-if="phase.skills.length > 0"
        class="phase-skill-row flex min-h-[124px] flex-nowrap items-stretch gap-3 overflow-x-auto w-full pb-1"
      >
        <!-- 技能卡片 -->
        <template v-for="(slot, si) in phase.skills" :key="si">
          <div class="phase-skill-item flex items-center gap-2 flex-shrink-0">
            <SkillCard
              :slot="slot"
              :index="si"
              :skill-name="skillNames[slot.skill_id] || null"
              :meta="skillMeta[slot.skill_id] || null"
              @edit="emit('editSlot', si)"
              @remove="emit('removeSlot', si)"
            />
            <!-- 箭头 -->
            <span
              v-if="si < phase.skills.length - 1"
              class="text-gray-500 text-base leading-none"
            >→</span>
          </div>
        </template>

        <!-- 添加按钮 -->
        <n-button size="small" dashed class="phase-add-card flex-shrink-0 h-[112px] w-28" @click="emit('addSlot')">
          <template #icon><IconPlus :size="16" /></template>
          添加技能
        </n-button>
      </div>
      <!-- 空状态 -->
      <div
        v-else
        class="phase-empty flex min-h-[124px] flex-col items-center justify-center gap-3 rounded border border-dashed border-white/10 bg-black/10 px-4 py-6 text-center"
      >
        <div>
          <div class="text-sm font-medium text-gray-300">当前阶段还没有技能</div>
          <div class="mt-1 text-xs text-gray-500">添加一个技能槽后，双击卡片可编辑条件、读条和完成检测</div>
        </div>
        <n-button size="small" type="primary" @click="emit('addSlot')">
          <template #icon><IconPlus :size="16" /></template>
          添加技能
        </n-button>
      </div>
    </div>

    <!-- 折叠态摘要 -->
    <div v-else class="phase-collapsed px-3 py-2 text-xs text-gray-500">
      {{ phase.skills.length }} 个技能 · {{ completeLabel(phase.complete_when) }}
    </div>
  </div>
</template>

<style scoped>
.phase-lane {
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: #121318;
}

.phase-header {
  display: grid;
  grid-template-columns: auto auto minmax(160px, 220px) minmax(220px, 320px) minmax(20px, 1fr) auto;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  background: rgb(255 255 255 / 4%);
  padding: 8px 12px;
}

.phase-header-spacer {
  min-width: 20px;
}

.phase-body {
  padding: 12px;
}

.phase-skill-row {
  display: flex;
  min-height: 124px;
  align-items: stretch;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  width: 100%;
}

.phase-skill-item {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.phase-add-card {
  flex: 0 0 112px;
  height: 112px;
}

.phase-empty {
  display: flex;
  min-height: 124px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(0 0 0 / 10%);
  padding: 24px 16px;
  text-align: center;
}

.phase-collapsed {
  padding: 8px 12px;
}

@media (max-width: 760px) {
  .phase-header {
    grid-template-columns: auto auto minmax(160px, 1fr) auto;
  }

  .phase-header :deep(.n-select) {
    grid-column: 3 / -1;
  }

  .phase-header-spacer {
    display: none;
  }
}
</style>
