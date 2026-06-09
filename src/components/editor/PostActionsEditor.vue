<script setup lang="ts">
import { computed } from "vue";
import { NButton, NInput, NInputNumber, NSelect, NTag } from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import type { RuntimeAction } from "../../types/cycle";
import {
  createDefaultRuntimeAction,
  markerValueOptions,
  runtimeActionTitle,
  type RuntimeActionType,
  type RuntimeCounterOption,
  type RuntimeMarkerOption,
  type RuntimeTimerOption,
} from "../../utils/runtime-actions";

const props = defineProps<{
  modelValue?: RuntimeAction[] | null;
  markerOptions?: RuntimeMarkerOption[];
  timerOptions?: RuntimeTimerOption[];
  counterOptions?: RuntimeCounterOption[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: RuntimeAction[]];
}>();

const actions = computed(() => props.modelValue ?? []);
const markerSelectOptions = computed(() =>
  (props.markerOptions ?? []).map((marker) => ({ label: marker.name || marker.id, value: marker.id }))
);
const timerSelectOptions = computed(() =>
  (props.timerOptions ?? []).map((timer) => ({ label: timer.name || timer.id, value: timer.id }))
);
const counterSelectOptions = computed(() =>
  (props.counterOptions ?? []).map((counter) => ({ label: counter.name || counter.id, value: counter.id }))
);
const actionTypeOptions = [
  { label: "设置标记", value: "set_marker" },
  { label: "清除标记", value: "clear_marker" },
  { label: "记录时间", value: "record_timer" },
  { label: "重置时间", value: "reset_timer" },
  { label: "增加计数", value: "increment_counter" },
  { label: "设置计数", value: "set_counter" },
  { label: "重置计数", value: "reset_counter" },
];

function cloneActions(): RuntimeAction[] {
  return actions.value.map((action) => ({ ...action }));
}

function update(next: RuntimeAction[]) {
  emit("update:modelValue", next);
}

function addAction(type: RuntimeActionType) {
  update([
    ...cloneActions(),
    createDefaultRuntimeAction(type, props.markerOptions, props.timerOptions, props.counterOptions),
  ]);
}

function removeAction(index: number) {
  const next = cloneActions();
  next.splice(index, 1);
  update(next);
}

function changeActionType(index: number, type: RuntimeActionType) {
  const next = cloneActions();
  next[index] = createDefaultRuntimeAction(type, props.markerOptions, props.timerOptions, props.counterOptions);
  update(next);
}

function updateAction(index: number, patch: Partial<RuntimeAction>) {
  const next = cloneActions();
  next[index] = { ...next[index], ...patch } as RuntimeAction;
  update(next);
}

function setMarkerId(index: number, markerId: string) {
  const values = markerValueOptions(props.markerOptions, markerId);
  updateAction(index, {
    marker_id: markerId,
    value: values[0] ?? "",
  } as Partial<RuntimeAction>);
}

function valueSelectOptions(markerId: string) {
  return markerValueOptions(props.markerOptions, markerId).map((value) => ({ label: value, value }));
}
</script>

<template>
  <div class="post-actions-editor rounded border border-white/10 bg-white/[0.03] p-3">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <div class="text-sm font-medium text-gray-100">执行后动作</div>
        <div class="mt-0.5 text-xs text-gray-500">技能确认成功后按顺序更新运行状态</div>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button size="tiny" secondary :disabled="markerSelectOptions.length === 0" @click="addAction('set_marker')">
          <template #icon><IconPlus /></template>
          设置标记
        </n-button>
        <n-button size="tiny" secondary :disabled="markerSelectOptions.length === 0" @click="addAction('clear_marker')">
          <template #icon><IconPlus /></template>
          清除标记
        </n-button>
        <n-button size="tiny" secondary :disabled="timerSelectOptions.length === 0" @click="addAction('record_timer')">
          <template #icon><IconPlus /></template>
          记录时间
        </n-button>
        <n-button size="tiny" secondary :disabled="timerSelectOptions.length === 0" @click="addAction('reset_timer')">
          <template #icon><IconPlus /></template>
          重置时间
        </n-button>
        <n-button size="tiny" secondary :disabled="counterSelectOptions.length === 0" @click="addAction('increment_counter')">
          <template #icon><IconPlus /></template>
          增加计数
        </n-button>
      </div>
    </div>

    <div v-if="actions.length === 0" class="post-actions-empty">
      暂无动作。先在“运行状态”中声明标记、时间标记或计数器。
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="(action, index) in actions"
        :key="`${action.type}-${index}`"
        class="post-action-row"
      >
        <n-tag size="small" :bordered="false">{{ runtimeActionTitle(action.type) }}</n-tag>
        <n-select
          :value="action.type"
          :options="actionTypeOptions"
          size="small"
          @update:value="(value) => changeActionType(index, value as RuntimeActionType)"
        />

        <template v-if="action.type === 'set_marker'">
          <n-select
            :value="action.marker_id"
            :options="markerSelectOptions"
            size="small"
            placeholder="标记"
            @update:value="(value) => setMarkerId(index, value)"
          />
          <n-select
            v-if="valueSelectOptions(action.marker_id).length > 0"
            :value="action.value"
            :options="valueSelectOptions(action.marker_id)"
            size="small"
            placeholder="值"
            @update:value="(value) => updateAction(index, { value } as Partial<RuntimeAction>)"
          />
          <n-input
            v-else
            :value="action.value"
            size="small"
            placeholder="值"
            @update:value="(value) => updateAction(index, { value } as Partial<RuntimeAction>)"
          />
        </template>

        <template v-else-if="action.type === 'clear_marker'">
          <n-select
            :value="action.marker_id"
            :options="markerSelectOptions"
            size="small"
            placeholder="标记"
            @update:value="(value) => updateAction(index, { marker_id: value } as Partial<RuntimeAction>)"
          />
        </template>

        <template v-else-if="action.type === 'record_timer' || action.type === 'reset_timer'">
          <n-select
            :value="action.timer_id"
            :options="timerSelectOptions"
            size="small"
            placeholder="时间标记"
            @update:value="(value) => updateAction(index, { timer_id: value } as Partial<RuntimeAction>)"
          />
        </template>

        <template v-else-if="action.type === 'increment_counter'">
          <n-select
            :value="action.counter_id"
            :options="counterSelectOptions"
            size="small"
            placeholder="计数器"
            @update:value="(value) => updateAction(index, { counter_id: value } as Partial<RuntimeAction>)"
          />
          <n-input-number
            :value="action.by"
            size="small"
            placeholder="增量"
            @update:value="(value) => updateAction(index, { by: value ?? 0 } as Partial<RuntimeAction>)"
          />
        </template>

        <template v-else-if="action.type === 'set_counter'">
          <n-select
            :value="action.counter_id"
            :options="counterSelectOptions"
            size="small"
            placeholder="计数器"
            @update:value="(value) => updateAction(index, { counter_id: value } as Partial<RuntimeAction>)"
          />
          <n-input-number
            :value="action.value"
            size="small"
            placeholder="值"
            @update:value="(value) => updateAction(index, { value: value ?? 0 } as Partial<RuntimeAction>)"
          />
        </template>

        <template v-else-if="action.type === 'reset_counter'">
          <n-select
            :value="action.counter_id"
            :options="counterSelectOptions"
            size="small"
            placeholder="计数器"
            @update:value="(value) => updateAction(index, { counter_id: value } as Partial<RuntimeAction>)"
          />
        </template>

        <n-button size="small" quaternary type="error" @click="removeAction(index)">
          <template #icon><IconTrash /></template>
        </n-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.post-action-row {
  display: grid;
  grid-template-columns: 72px minmax(104px, 0.9fr) minmax(120px, 1fr) minmax(110px, 1fr) 34px;
  gap: 8px;
  align-items: center;
}

.post-actions-empty {
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 6px;
  padding: 12px;
  color: rgb(156 163 175);
  font-size: 12px;
}

@media (max-width: 640px) {
  .post-action-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .post-action-row :deep(.n-button) {
    justify-self: flex-start;
  }
}
</style>
