<script setup lang="ts">
import { computed } from "vue";
import {
  NButton,
  NInput,
  NInputNumber,
  NPopconfirm,
  NSelect,
  NSwitch,
  NTag,
} from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import SkillCard from "./SkillCard.vue";
import type { AssistInterruptPolicy, AssistLaneConfig } from "../../types/cycle";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

const props = defineProps<{
  lanes: AssistLaneConfig[];
  skillNames: Record<string, string>;
  skillMeta: Record<string, SkillCardMeta>;
}>();

const emit = defineEmits<{
  "update:lanes": [lanes: AssistLaneConfig[]];
  "add-slot": [laneIndex: number];
  "edit-slot": [laneIndex: number, slotIndex: number];
  "remove-slot": [laneIndex: number, slotIndex: number];
}>();

const interruptOptions: { label: string; value: AssistInterruptPolicy }[] = [
  { label: "仅主循环空闲", value: "idle_only" },
  { label: "允许完成等待期", value: "complete_wait" },
  { label: "允许任意等待期", value: "any_wait" },
];

const enabledLaneCount = computed(() => props.lanes.filter((lane) => lane.enabled).length);
const totalAssistSlots = computed(() =>
  props.lanes.reduce((count, lane) => count + lane.skills.length, 0)
);

function notifyChanged() {
  emit("update:lanes", [...props.lanes]);
}

function nextLaneId(): string {
  const used = new Set(props.lanes.map((lane) => lane.id.trim()));
  for (let i = props.lanes.length + 1; i < props.lanes.length + 100; i += 1) {
    const id = `assist_${i}`;
    if (!used.has(id)) return id;
  }
  return `assist_${Date.now()}`;
}

function addLane() {
  const nextIndex = props.lanes.length + 1;
  props.lanes.push({
    id: nextLaneId(),
    name: `辅助 ${nextIndex}`,
    enabled: true,
    check_interval_ms: 250,
    interrupt_policy: "idle_only",
    skills: [],
  });
  notifyChanged();
}

function removeLane(index: number) {
  props.lanes.splice(index, 1);
  notifyChanged();
}

function updateLane(index: number, patch: Partial<AssistLaneConfig>) {
  Object.assign(props.lanes[index], patch);
  notifyChanged();
}

function removeSlot(laneIndex: number, slotIndex: number) {
  emit("remove-slot", laneIndex, slotIndex);
}
</script>

<template>
  <section class="assist-lane-panel flex min-w-0 flex-col rounded border border-white/10 bg-white/[0.02]">
    <div class="assist-lane-header flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-gray-100">辅助 Lane</h2>
          <n-tag size="small" :bordered="false">启用 {{ enabledLaneCount }}</n-tag>
          <n-tag size="small" :bordered="false">技能 {{ totalAssistSlots }}</n-tag>
        </div>
        <p class="mt-0.5 text-xs text-gray-500">后台补放技能配置；执行时按检查间隔和打断策略调度</p>
      </div>
      <n-button size="small" secondary @click="addLane">
        <template #icon><IconPlus /></template>
        添加辅助 Lane
      </n-button>
    </div>

    <div class="assist-lane-body space-y-3 p-4">
      <div v-if="lanes.length === 0" class="rounded border border-dashed border-white/10 px-4 py-6 text-center text-xs text-gray-500">
        暂无辅助 Lane。适合配置咒语补放、短 CD 增益补放等后台动作。
      </div>

      <div
        v-for="(lane, laneIndex) in lanes"
        :key="lane.id || laneIndex"
        class="assist-lane-row rounded border border-white/10 bg-black/10 p-3"
      >
        <div class="assist-lane-controls grid gap-2">
          <div class="flex items-center gap-2">
            <n-switch
              :value="lane.enabled"
              size="small"
              @update:value="(value) => updateLane(laneIndex, { enabled: value })"
            />
            <span class="text-xs text-gray-400">启用</span>
          </div>
          <n-input
            :value="lane.id"
            size="small"
            placeholder="assist_id"
            @update:value="(value) => updateLane(laneIndex, { id: value })"
          />
          <n-input
            :value="lane.name"
            size="small"
            placeholder="显示名称"
            @update:value="(value) => updateLane(laneIndex, { name: value })"
          />
          <n-input-number
            :value="lane.check_interval_ms"
            size="small"
            :min="10"
            :max="600000"
            :step="10"
            placeholder="检查间隔(ms)"
            @update:value="(value) => updateLane(laneIndex, { check_interval_ms: value ?? 250 })"
          />
          <n-select
            :value="lane.interrupt_policy"
            size="small"
            :options="interruptOptions"
            @update:value="(value) => updateLane(laneIndex, { interrupt_policy: value as AssistInterruptPolicy })"
          />
          <n-popconfirm @positive-click="removeLane(laneIndex)">
            <template #trigger>
              <n-button size="small" quaternary circle type="error">
                <template #icon><IconTrash /></template>
              </n-button>
            </template>
            删除该辅助 Lane？
          </n-popconfirm>
        </div>

        <div class="assist-skill-row mt-3 flex min-h-[124px] flex-nowrap items-stretch gap-3 overflow-x-auto pb-1">
          <template v-for="(slot, slotIndex) in lane.skills" :key="slotIndex">
            <SkillCard
              :slot="slot"
              :index="slotIndex"
              :skill-name="skillNames[slot.skill_id] ?? null"
              :meta="skillMeta[slot.skill_id] ?? null"
              @edit="emit('edit-slot', laneIndex, slotIndex)"
              @remove="removeSlot(laneIndex, slotIndex)"
            />
          </template>
          <n-button size="small" dashed class="assist-add-card h-[112px] w-32 flex-shrink-0" @click="emit('add-slot', laneIndex)">
            <template #icon><IconPlus /></template>
            添加技能
          </n-button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.assist-lane-panel {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 2%);
}

.assist-lane-header {
  border-bottom: 1px solid rgb(255 255 255 / 10%);
}

.assist-lane-controls {
  grid-template-columns: 96px minmax(120px, 180px) minmax(140px, 1fr) 150px 170px 36px;
  align-items: center;
}

.assist-add-card {
  height: 112px;
  width: 128px;
}

@media (max-width: 900px) {
  .assist-lane-controls {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
