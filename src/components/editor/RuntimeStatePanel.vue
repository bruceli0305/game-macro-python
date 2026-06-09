<script setup lang="ts">
import { computed } from "vue";
import { NButton, NInput, NInputNumber, NSwitch, NTag } from "naive-ui";
import { IconPlus, IconTrash } from "@tabler/icons-vue";
import type {
  CycleStateSchema,
  RuntimeCounterDef,
  RuntimeMarkerDef,
  RuntimeTimerDef,
} from "../../types/cycle";
import {
  createDefaultRuntimeCounter,
  createDefaultRuntimeMarker,
  createDefaultRuntimeTimer,
  parseAllowedMarkerValues,
} from "../../utils/runtime-state-schema";

const props = defineProps<{
  modelValue?: CycleStateSchema | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: CycleStateSchema];
}>();

const schema = computed<CycleStateSchema>(() => ({
  markers: props.modelValue?.markers ?? [],
  timers: props.modelValue?.timers ?? [],
  counters: props.modelValue?.counters ?? [],
}));

function cloneSchema(): CycleStateSchema {
  return {
    markers: schema.value.markers.map((marker) => ({
      ...marker,
      allowed_values: [...(marker.allowed_values ?? [])],
    })),
    timers: schema.value.timers.map((timer) => ({ ...timer })),
    counters: schema.value.counters.map((counter) => ({ ...counter })),
  };
}

function update(next: CycleStateSchema) {
  emit("update:modelValue", next);
}

function addMarker() {
  const next = cloneSchema();
  next.markers.push(
    createDefaultRuntimeMarker(
      next.markers.map((marker) => marker.id),
      next.markers.length
    )
  );
  update(next);
}

function updateMarker(index: number, patch: Partial<RuntimeMarkerDef>) {
  const next = cloneSchema();
  next.markers[index] = { ...next.markers[index], ...patch };
  update(next);
}

function removeMarker(index: number) {
  const next = cloneSchema();
  next.markers.splice(index, 1);
  update(next);
}

function addTimer() {
  const next = cloneSchema();
  next.timers.push(
    createDefaultRuntimeTimer(
      next.timers.map((timer) => timer.id),
      next.timers.length
    )
  );
  update(next);
}

function updateTimer(index: number, patch: Partial<RuntimeTimerDef>) {
  const next = cloneSchema();
  next.timers[index] = { ...next.timers[index], ...patch };
  update(next);
}

function removeTimer(index: number) {
  const next = cloneSchema();
  next.timers.splice(index, 1);
  update(next);
}

function addCounter() {
  const next = cloneSchema();
  next.counters.push(
    createDefaultRuntimeCounter(
      next.counters.map((counter) => counter.id),
      next.counters.length
    )
  );
  update(next);
}

function updateCounter(index: number, patch: Partial<RuntimeCounterDef>) {
  const next = cloneSchema();
  next.counters[index] = { ...next.counters[index], ...patch };
  update(next);
}

function removeCounter(index: number) {
  const next = cloneSchema();
  next.counters.splice(index, 1);
  update(next);
}
</script>

<template>
  <section class="runtime-state-panel rounded border border-white/10 bg-white/[0.02]">
    <div class="runtime-state-header flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
      <div>
        <h2 class="text-sm font-semibold text-gray-100">运行状态</h2>
        <p class="mt-0.5 text-xs text-gray-500">声明循环条件和动作可引用的标记、时间标记与计数器</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button size="tiny" secondary @click="addMarker">
          <template #icon><IconPlus /></template>
          标记
        </n-button>
        <n-button size="tiny" secondary @click="addTimer">
          <template #icon><IconPlus /></template>
          时间
        </n-button>
        <n-button size="tiny" secondary @click="addCounter">
          <template #icon><IconPlus /></template>
          计数器
        </n-button>
      </div>
    </div>

    <div class="runtime-state-body grid gap-4 p-4 xl:grid-cols-3">
      <div class="runtime-state-group min-w-0">
        <div class="mb-2 flex items-center gap-2">
          <span class="text-xs font-semibold text-gray-300">运行标记</span>
          <n-tag size="small" :bordered="false">{{ schema.markers.length }}</n-tag>
        </div>
        <div v-if="schema.markers.length === 0" class="runtime-state-empty">
          暂无标记。用于表达 weapon=main、f1_state=open 这类状态。
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(marker, index) in schema.markers"
            :key="`${marker.id}-${index}`"
            class="runtime-state-row runtime-state-row-marker"
          >
            <n-input :value="marker.id" size="small" placeholder="id" @update:value="(value) => updateMarker(index, { id: value })" />
            <n-input :value="marker.name" size="small" placeholder="名称" @update:value="(value) => updateMarker(index, { name: value })" />
            <n-input :value="marker.initial_value" size="small" placeholder="初始值" @update:value="(value) => updateMarker(index, { initial_value: value })" />
            <n-input
              :value="marker.allowed_values.join(', ')"
              size="small"
              placeholder="允许值，用逗号分隔"
              @update:value="(value) => updateMarker(index, { allowed_values: parseAllowedMarkerValues(value) })"
            />
            <n-button size="small" quaternary type="error" @click="removeMarker(index)">
              <template #icon><IconTrash /></template>
            </n-button>
          </div>
        </div>
      </div>

      <div class="runtime-state-group min-w-0">
        <div class="mb-2 flex items-center gap-2">
          <span class="text-xs font-semibold text-gray-300">时间标记</span>
          <n-tag size="small" :bordered="false">{{ schema.timers.length }}</n-tag>
        </div>
        <div v-if="schema.timers.length === 0" class="runtime-state-empty">
          暂无时间标记。用于表达 last_burst 已经过 8000ms 这类条件。
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(timer, index) in schema.timers"
            :key="`${timer.id}-${index}`"
            class="runtime-state-row runtime-state-row-timer"
          >
            <n-input :value="timer.id" size="small" placeholder="id" @update:value="(value) => updateTimer(index, { id: value })" />
            <n-input :value="timer.name" size="small" placeholder="名称" @update:value="(value) => updateTimer(index, { name: value })" />
            <label class="runtime-state-switch">
              <n-switch :value="timer.reset_on_cycle_start" size="small" @update:value="(value) => updateTimer(index, { reset_on_cycle_start: value })" />
              <span>循环开始重置</span>
            </label>
            <n-button size="small" quaternary type="error" @click="removeTimer(index)">
              <template #icon><IconTrash /></template>
            </n-button>
          </div>
        </div>
      </div>

      <div class="runtime-state-group min-w-0">
        <div class="mb-2 flex items-center gap-2">
          <span class="text-xs font-semibold text-gray-300">计数器</span>
          <n-tag size="small" :bordered="false">{{ schema.counters.length }}</n-tag>
        </div>
        <div v-if="schema.counters.length === 0" class="runtime-state-empty">
          暂无计数器。用于表达 main_wp2_count >= 2 这类阶段门控。
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(counter, index) in schema.counters"
            :key="`${counter.id}-${index}`"
            class="runtime-state-row runtime-state-row-counter"
          >
            <n-input :value="counter.id" size="small" placeholder="id" @update:value="(value) => updateCounter(index, { id: value })" />
            <n-input :value="counter.name" size="small" placeholder="名称" @update:value="(value) => updateCounter(index, { name: value })" />
            <n-input-number
              :value="counter.initial_value"
              size="small"
              placeholder="初始值"
              @update:value="(value) => updateCounter(index, { initial_value: value ?? 0 })"
            />
            <label class="runtime-state-switch">
              <n-switch :value="counter.reset_on_phase_entry" size="small" @update:value="(value) => updateCounter(index, { reset_on_phase_entry: value })" />
              <span>进阶段重置</span>
            </label>
            <label class="runtime-state-switch">
              <n-switch :value="counter.reset_on_cycle_start" size="small" @update:value="(value) => updateCounter(index, { reset_on_cycle_start: value })" />
              <span>循环开始重置</span>
            </label>
            <n-button size="small" quaternary type="error" @click="removeCounter(index)">
              <template #icon><IconTrash /></template>
            </n-button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.runtime-state-panel {
  overflow: hidden;
}

.runtime-state-row {
  display: grid;
  gap: 8px;
  align-items: center;
}

.runtime-state-row-marker {
  grid-template-columns: minmax(92px, 0.8fr) minmax(110px, 1fr) minmax(92px, 0.8fr) minmax(150px, 1.3fr) 34px;
}

.runtime-state-row-timer {
  grid-template-columns: minmax(100px, 1fr) minmax(120px, 1fr) minmax(130px, auto) 34px;
}

.runtime-state-row-counter {
  grid-template-columns: minmax(96px, 1fr) minmax(110px, 1fr) 96px minmax(110px, auto) minmax(130px, auto) 34px;
}

.runtime-state-empty {
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 6px;
  padding: 12px;
  color: rgb(156 163 175);
  font-size: 12px;
}

.runtime-state-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: rgb(209 213 219);
  font-size: 12px;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .runtime-state-row-marker,
  .runtime-state-row-timer,
  .runtime-state-row-counter {
    grid-template-columns: minmax(0, 1fr);
  }

  .runtime-state-row :deep(.n-button) {
    justify-self: flex-start;
  }
}
</style>
