<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { NButton, NSelect, NTag, useMessage } from "naive-ui";
import { IconPlayerPlay, IconPlayerStop, IconTrash } from "@tabler/icons-vue";
import { useDebugRun } from "../composables/useDebugRun";
import { useProfile } from "../composables/useProfile";
import type { CycleConfig } from "../types/cycle";

const message = useMessage();
const { loadActiveProfile } = useProfile();
const debugRun = useDebugRun();

const rotation = ref<CycleConfig | null>(null);
const loadingProfile = ref(false);
const startPhase = ref(0);
const endPhase = ref(0);

const phaseOptions = computed(() =>
  (rotation.value?.phases ?? []).map((phase, index) => ({
    label: `P${index + 1} ${phase.name || "未命名阶段"}`,
    value: index,
  }))
);

const canRun = computed(
  () =>
    !debugRun.isRunning.value &&
    phaseOptions.value.length > 0 &&
    startPhase.value <= endPhase.value
);

const currentPhaseLabel = computed(() => {
  const last = debugRun.logs.value[debugRun.logs.value.length - 1];
  if (!last) return "-";
  return `P${last.phase_index + 1} ${last.phase_name || ""}`.trim();
});

const statusType = computed(() => {
  switch (debugRun.status.value) {
    case "running":
      return "info";
    case "completed":
      return "success";
    case "failed":
      return "error";
    case "stopped":
      return "warning";
    default:
      return "default";
  }
});

function outcomeType(outcome: string) {
  switch (outcome) {
    case "SUCCESS":
      return "success";
    case "FAILED":
      return "error";
    case "NOT_READY":
    case "SKIP":
      return "warning";
    case "STOPPED":
      return "default";
    default:
      return "info";
  }
}

async function loadProfile() {
  loadingProfile.value = true;
  try {
    const profile = await loadActiveProfile();
    rotation.value = profile.rotations[0] ?? null;
    startPhase.value = 0;
    endPhase.value = 0;
  } catch (error) {
    message.error(errorMessage(error, "加载当前配置失败"));
  } finally {
    loadingProfile.value = false;
  }
}

async function runOnce() {
  if (!canRun.value) return;
  try {
    await debugRun.runOnce(startPhase.value, endPhase.value);
  } catch (error) {
    message.error(errorMessage(error, "调试运行启动失败"));
  }
}

async function stopRun() {
  try {
    await debugRun.stop();
  } catch (error) {
    message.error(errorMessage(error, "停止调试运行失败"));
  }
}

function errorMessage(error: unknown, fallback: string): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

onMounted(() => {
  void debugRun.ensureListeners();
  void loadProfile();
});
</script>

<template>
  <main class="debug-panel">
    <header class="debug-header">
      <div>
        <h1>循环调试</h1>
        <p>单次阶段范围验证</p>
      </div>
      <n-tag size="small" type="success">置顶</n-tag>
    </header>

    <section class="debug-section">
      <div class="section-title">阶段范围</div>
      <div class="phase-row">
        <n-select
          v-model:value="startPhase"
          size="small"
          :options="phaseOptions"
          :loading="loadingProfile"
          :disabled="debugRun.isRunning.value"
        />
        <span class="arrow">→</span>
        <n-select
          v-model:value="endPhase"
          size="small"
          :options="phaseOptions"
          :loading="loadingProfile"
          :disabled="debugRun.isRunning.value"
        />
      </div>
      <div v-if="startPhase > endPhase" class="range-error">
        起始阶段不能晚于结束阶段
      </div>
    </section>

    <section class="debug-controls">
      <n-button
        type="primary"
        size="small"
        :disabled="!canRun"
        :loading="debugRun.isRunning.value"
        @click="runOnce"
      >
        <template #icon><IconPlayerPlay /></template>
        单次运行
      </n-button>
      <n-button size="small" :disabled="!debugRun.isRunning.value" @click="stopRun">
        <template #icon><IconPlayerStop /></template>
        停止
      </n-button>
      <n-button size="small" secondary @click="debugRun.clearLogs">
        <template #icon><IconTrash /></template>
        清空
      </n-button>
      <n-tag size="small" :type="statusType">{{ debugRun.status.value }}</n-tag>
    </section>

    <section class="debug-summary">
      <div>
        <span>当前阶段</span>
        <strong>{{ currentPhaseLabel }}</strong>
      </div>
      <div>
        <span>事件</span>
        <strong>{{ debugRun.logs.value.length }}</strong>
      </div>
      <div>
        <span>耗时</span>
        <strong>{{ debugRun.elapsedMs.value }}ms</strong>
      </div>
      <div v-if="debugRun.latestError.value" class="summary-error">
        {{ debugRun.latestError.value }}
      </div>
    </section>

    <section class="debug-log">
      <div class="log-header">
        <span>发键记录</span>
        <small>{{ debugRun.runId.value || "no run" }}</small>
      </div>

      <div v-if="debugRun.logs.value.length === 0" class="empty-log">
        暂无调试事件
      </div>
      <article
        v-for="(log, index) in debugRun.logs.value"
        v-else
        :key="`${log.run_id}-${index}-${log.ts_ms}`"
        class="log-row"
      >
        <div class="log-top">
          <n-tag size="small" :type="outcomeType(log.outcome)">
            {{ log.outcome }}
          </n-tag>
          <strong>P{{ log.phase_index + 1 }} {{ log.skill_name || log.skill_id || log.event }}</strong>
          <span>{{ log.ts_ms }}ms</span>
        </div>
        <div class="log-meta">
          <span>{{ log.phase_name || "-" }}</span>
          <span>key={{ log.key || "-" }}</span>
          <span>{{ log.event }}</span>
        </div>
        <div class="log-reason">{{ log.reason || "ok" }}</div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.debug-panel {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
  gap: 10px;
  background: #17181c;
  color: #e5e7eb;
  padding: 12px;
}

.debug-header,
.debug-controls,
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.debug-header h1 {
  color: #f9fafb;
  font-size: 16px;
  font-weight: 800;
}

.debug-header p,
.section-title,
.debug-summary span,
.log-header small,
.log-meta,
.log-reason,
.range-error,
.empty-log {
  color: #9ca3af;
  font-size: 12px;
}

.debug-section,
.debug-summary,
.debug-log {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 3%);
}

.debug-section {
  padding: 10px;
}

.section-title {
  margin-bottom: 6px;
  font-weight: 700;
}

.phase-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.arrow {
  color: #6b7280;
}

.range-error {
  margin-top: 6px;
  color: #fca5a5;
}

.debug-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
}

.debug-summary div {
  min-width: 0;
}

.debug-summary strong {
  display: block;
  overflow: hidden;
  color: #f3f4f6;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-error {
  grid-column: 1 / -1;
  color: #fca5a5;
  font-size: 12px;
}

.debug-log {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.log-header {
  flex: 0 0 auto;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  padding: 8px 10px;
}

.empty-log {
  padding: 18px 10px;
  text-align: center;
}

.log-row {
  border-bottom: 1px solid rgb(255 255 255 / 7%);
  padding: 8px 10px;
}

.log-top {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
}

.log-top strong {
  overflow: hidden;
  color: #f9fafb;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-top span {
  color: #9ca3af;
  font-size: 11px;
}

.log-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 5px;
}

.log-reason {
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: #d1d5db;
}
</style>
