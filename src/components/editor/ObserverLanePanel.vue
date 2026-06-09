<script setup lang="ts">
import { computed } from "vue";
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NInput,
  NInputNumber,
  NPopconfirm,
  NSwitch,
  NTag,
} from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import ConditionBuilder from "./ConditionBuilder.vue";
import PostActionsEditor from "./PostActionsEditor.vue";
import type { Expr } from "../../types/ast";
import type { ObserverActionSlot, ObserverLaneConfig, RuntimeAction } from "../../types/cycle";

const props = defineProps<{
  lanes: ObserverLaneConfig[];
  skillOptions: { id: string; name: string }[];
  pointOptions: { id: string; name: string }[];
  markerOptions: { id: string; name: string; allowed_values?: string[] }[];
  timerOptions: { id: string; name: string }[];
  counterOptions: { id: string; name: string }[];
}>();

const emit = defineEmits<{
  "update:lanes": [lanes: ObserverLaneConfig[]];
}>();

const enabledLaneCount = computed(() => props.lanes.filter((lane) => lane.enabled).length);
const actionSlotCount = computed(() =>
  props.lanes.reduce((count, lane) => count + lane.actions.length, 0)
);

function notifyChanged() {
  emit("update:lanes", [...props.lanes]);
}

function nextLaneId(): string {
  const used = new Set(props.lanes.map((lane) => lane.id.trim()));
  for (let i = props.lanes.length + 1; i < props.lanes.length + 100; i += 1) {
    const id = `observer_${i}`;
    if (!used.has(id)) return id;
  }
  return `observer_${Date.now()}`;
}

function nextActionId(lane: ObserverLaneConfig): string {
  const used = new Set(lane.actions.map((action) => action.id.trim()));
  for (let i = lane.actions.length + 1; i < lane.actions.length + 100; i += 1) {
    const id = `action_${i}`;
    if (!used.has(id)) return id;
  }
  return `action_${Date.now()}`;
}

function addLane() {
  const nextIndex = props.lanes.length + 1;
  props.lanes.push({
    id: nextLaneId(),
    name: `观察 ${nextIndex}`,
    enabled: true,
    check_interval_ms: 50,
    actions: [],
  });
  notifyChanged();
}

function removeLane(index: number) {
  props.lanes.splice(index, 1);
  notifyChanged();
}

function updateLane(index: number, patch: Partial<ObserverLaneConfig>) {
  Object.assign(props.lanes[index], patch);
  notifyChanged();
}

function addAction(laneIndex: number) {
  const lane = props.lanes[laneIndex];
  if (!lane) return;
  lane.actions.push({
    id: nextActionId(lane),
    label: `动作 ${lane.actions.length + 1}`,
    priority: lane.actions.length + 1,
    condition_expr: null,
    actions: [],
  });
  notifyChanged();
}

function removeAction(laneIndex: number, actionIndex: number) {
  props.lanes[laneIndex]?.actions.splice(actionIndex, 1);
  notifyChanged();
}

function updateAction(laneIndex: number, actionIndex: number, patch: Partial<ObserverActionSlot>) {
  const action = props.lanes[laneIndex]?.actions[actionIndex];
  if (!action) return;
  Object.assign(action, patch);
  notifyChanged();
}

function updateCondition(laneIndex: number, actionIndex: number, value: Expr | null) {
  updateAction(laneIndex, actionIndex, { condition_expr: value as Record<string, unknown> | null });
}

function updateRuntimeActions(laneIndex: number, actionIndex: number, actions: RuntimeAction[]) {
  updateAction(laneIndex, actionIndex, { actions });
}
</script>

<template>
  <section class="observer-lane-panel flex min-w-0 flex-col rounded border border-white/10 bg-white/[0.02]">
    <div class="observer-lane-header flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-gray-100">观察动作 Lane</h2>
          <n-tag size="small" :bordered="false">启用 {{ enabledLaneCount }}</n-tag>
          <n-tag size="small" :bordered="false">动作 {{ actionSlotCount }}</n-tag>
        </div>
        <p class="mt-0.5 text-xs text-gray-500">用于监听 ROI、像素、标记或计时条件，只更新运行状态，不发送按键。</p>
      </div>
      <n-button size="small" secondary @click="addLane">
        <template #icon><IconPlus /></template>
        添加观察 Lane
      </n-button>
    </div>

    <div class="observer-lane-body space-y-3 p-4">
      <div v-if="lanes.length === 0" class="rounded border border-dashed border-white/10 px-4 py-6 text-center text-xs text-gray-500">
        暂无观察 Lane。适合配置“检测到施法条出现后记录时间”等状态机前置动作。
      </div>

      <div
        v-for="(lane, laneIndex) in lanes"
        :key="lane.id || laneIndex"
        class="observer-lane-row rounded border border-white/10 bg-black/10 p-3"
      >
        <div class="observer-lane-controls grid gap-2">
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
            placeholder="observer_id"
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
            @update:value="(value) => updateLane(laneIndex, { check_interval_ms: value ?? 50 })"
          />
          <n-popconfirm @positive-click="removeLane(laneIndex)">
            <template #trigger>
              <n-button size="small" quaternary circle type="error">
                <template #icon><IconTrash /></template>
              </n-button>
            </template>
            删除该观察 Lane？
          </n-popconfirm>
        </div>

        <div class="mt-3 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-xs font-medium text-gray-300">动作槽</div>
            <n-button size="tiny" secondary @click="addAction(laneIndex)">
              <template #icon><IconPlus /></template>
              添加动作
            </n-button>
          </div>

          <div v-if="lane.actions.length === 0" class="rounded border border-dashed border-white/10 px-3 py-5 text-center text-xs text-gray-500">
            暂无动作。添加后可配置触发条件和要写入的标记、时间或计数器。
          </div>

          <n-collapse v-else>
            <n-collapse-item
              v-for="(action, actionIndex) in lane.actions"
              :key="action.id || actionIndex"
              :name="`${laneIndex}-${actionIndex}`"
            >
              <template #header>
                <div class="observer-action-header">
                  <n-tag size="small" :bordered="false">P{{ action.priority }}</n-tag>
                  <span class="truncate">{{ action.label || action.id || `动作 ${actionIndex + 1}` }}</span>
                </div>
              </template>

              <div class="observer-action-body space-y-3">
                <div class="observer-action-controls grid gap-2">
                  <n-input
                    :value="action.id"
                    size="small"
                    placeholder="action_id"
                    @update:value="(value) => updateAction(laneIndex, actionIndex, { id: value })"
                  />
                  <n-input
                    :value="action.label"
                    size="small"
                    placeholder="显示名称"
                    @update:value="(value) => updateAction(laneIndex, actionIndex, { label: value })"
                  />
                  <n-input-number
                    :value="action.priority"
                    size="small"
                    :min="1"
                    :max="999"
                    @update:value="(value) => updateAction(laneIndex, actionIndex, { priority: value ?? 1 })"
                  />
                  <n-popconfirm @positive-click="removeAction(laneIndex, actionIndex)">
                    <template #trigger>
                      <n-button size="small" quaternary circle type="error">
                        <template #icon><IconTrash /></template>
                      </n-button>
                    </template>
                    删除该动作？
                  </n-popconfirm>
                </div>

                <div class="observer-editor-block">
                  <div class="mb-2 text-xs font-medium text-gray-300">触发条件</div>
                  <ConditionBuilder
                    :model-value="action.condition_expr as Expr | null"
                    :skills="skillOptions"
                    :points="pointOptions"
                    :markers="markerOptions"
                    :timers="timerOptions"
                    :counters="counterOptions"
                    @update:model-value="(value) => updateCondition(laneIndex, actionIndex, value)"
                  />
                </div>

                <PostActionsEditor
                  :model-value="action.actions"
                  :marker-options="markerOptions"
                  :timer-options="timerOptions"
                  :counter-options="counterOptions"
                  @update:model-value="(value) => updateRuntimeActions(laneIndex, actionIndex, value)"
                />
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.observer-lane-panel {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 2%);
}

.observer-lane-header {
  border-bottom: 1px solid rgb(255 255 255 / 10%);
}

.observer-lane-controls {
  grid-template-columns: 96px minmax(120px, 180px) minmax(140px, 1fr) 150px 36px;
  align-items: center;
}

.observer-action-header {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.observer-action-controls {
  grid-template-columns: minmax(120px, 180px) minmax(140px, 1fr) 120px 36px;
  align-items: center;
}

.observer-editor-block {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 3%);
  padding: 12px;
}

@media (max-width: 900px) {
  .observer-lane-controls,
  .observer-action-controls {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
