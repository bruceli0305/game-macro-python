<script setup lang="ts">
import { NButton, NInput, NSelect, NPopconfirm } from "naive-ui";
import { IconPlus, IconTrash, IconChevronDown, IconChevronRight } from "@tabler/icons-vue";
import SkillCard from "./SkillCard.vue";
import type { CyclePhase } from "../../types/cycle";

defineProps<{
  phase: CyclePhase;
  phaseIndex: number;
  skillNames: Record<string, string>;
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
  <div class="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
    <!-- Phase 头部 -->
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 bg-white/[0.04] border-b border-white/10">
      <n-button size="tiny" quaternary @click="emit('toggleCollapse')">
        <template #icon>
          <IconChevronDown v-if="!collapsed" :size="14" />
          <IconChevronRight v-else :size="14" />
        </template>
      </n-button>
      <span class="text-xs font-bold text-gray-300 whitespace-nowrap">P{{ phaseIndex + 1 }}</span>
      <n-input
        :value="phase.name"
        size="tiny"
        placeholder="名称"
        style="width:100px"
        @update:value="(v: string) => { phase.name = v; emit('update:phase', phase); }"
      />
      <n-select
        :value="phase.complete_when"
        :options="completeOptions"
        size="tiny"
        style="width:150px"
        @update:value="(v: string) => { phase.complete_when = v as any; emit('update:phase', phase); }"
      />
      <div class="flex-1 min-w-[20px]" />
      <n-popconfirm @positive-click="emit('remove')">
        <template #trigger>
          <n-button size="tiny" quaternary type="error">
            <template #icon><IconTrash :size="14" /></template>
          </n-button>
        </template>
        删除？
      </n-popconfirm>
    </div>

    <!-- 卡片区域（可折叠） -->
    <div v-if="!collapsed" class="px-3 py-3">
      <div class="flex flex-nowrap items-start gap-2 overflow-x-auto w-full" style="scrollbar-width:thin">
        <!-- 技能卡片 -->
        <template v-for="(slot, si) in phase.skills" :key="si">
          <div class="flex items-center gap-2 flex-shrink-0">
            <SkillCard
              :slot="slot"
              :index="si"
              :skill-name="skillNames[slot.skill_id] || null"
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
        <n-button size="small" dashed class="flex-shrink-0 h-[72px] w-24" @click="emit('addSlot')">
          <template #icon><IconPlus :size="16" /></template>
          添加技能
        </n-button>
      </div>
      <!-- 空状态 -->
      <div v-if="phase.skills.length === 0" class="text-xs text-gray-500 py-1">
        暂无技能，点击「添加技能」或双击已有卡片编辑
      </div>
    </div>

    <!-- 折叠态摘要 -->
    <div v-else class="px-3 py-2 text-xs text-gray-500">
      {{ phase.skills.length }} 个技能 · {{ completeLabel(phase.complete_when) }}
    </div>
  </div>
</template>
