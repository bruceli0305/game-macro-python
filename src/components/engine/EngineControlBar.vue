<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NSpace, NTag, useMessage } from "naive-ui";
import { IconBug, IconPlayerPlay, IconPlayerStop, IconRefresh } from "@tabler/icons-vue";
import { useEngine, type EnginePreflightReport } from "../../composables/useEngine";
import { useEnginePreflight } from "../../composables/useEnginePreflight";
import { useDebugRun } from "../../composables/useDebugRun";

const { start, stop, preflight, store } = useEngine();
const { validateEngineStart } = useEnginePreflight();
const { openPanel } = useDebugRun();
const message = useMessage();
const backendPreflightRunning = ref(false);
const backendPreflight = ref<EnginePreflightReport | null>(null);
const backendPreflightSkipped = ref(false);

const backendPreflightTagType = computed(() => {
  if (backendPreflightSkipped.value) return "warning";
  if (!backendPreflight.value) return "default";
  return backendPreflight.value.ready ? "success" : "error";
});

const backendPreflightStatus = computed(() => {
  if (backendPreflightSkipped.value) return "跳过";
  if (!backendPreflight.value) return "未运行";
  return backendPreflight.value.ready ? "通过" : "失败";
});

const backendPreflightDetail = computed(() => {
  if (backendPreflightSkipped.value) return "Tauri IPC runtime unavailable";
  if (!backendPreflight.value) return "";
  const report = backendPreflight.value;
  if (report.ready) {
    return `${report.profile_name}: skills=${report.skill_count}, slots=${report.executable_slot_count}`;
  }
  return report.error || "backend preflight failed";
});

const castBarRoiDetail = computed(() => {
  const stats = store.castBarRoi;
  if (!stats) return "";
  const lastMs = (stats.lastLatencyUs / 1000).toFixed(1);
  const avgMs = (stats.avgLatencyUs / 1000).toFixed(1);
  const maxMs = (stats.maxLatencyUs / 1000).toFixed(1);
  const cache = stats.sampleCount > 0
    ? `${stats.cacheHitCount}/${stats.sampleCount + stats.cacheHitCount}`
    : `${stats.cacheHitCount}/0`;
  const signal = stats.lastGone
    ? "消失"
    : stats.lastChangedFromBaseline || stats.lastBorderVisible
      ? "可见"
      : "未命中";
  const error = stats.lastError ? ` · ${stats.lastError}` : "";
  return `ROI ${signal} · last ${lastMs}ms · avg ${avgMs}ms · max ${maxMs}ms · cache ${cache}${error}`;
});

function hasTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as Window & { __TAURI_INTERNALS__?: unknown })
  );
}

async function startWithValidation() {
  try {
    const error = await validateEngineStart();
    if (error) {
      message.error(error);
      return;
    }
    await start();
    message.success("引擎已启动");
  } catch (e) {
    message.error(String(e || "引擎启动失败"));
  }
}

async function stopEngine() {
  await stop();
  message.info("引擎已停止");
}

async function runBackendPreflight() {
  backendPreflightRunning.value = true;
  backendPreflight.value = null;
  backendPreflightSkipped.value = false;
  try {
    if (!hasTauriRuntime()) {
      backendPreflightSkipped.value = true;
      message.warning("后端预检已跳过：当前不是 Tauri 运行环境");
      return;
    }

    const report = await preflight();
    backendPreflight.value = report;
    if (report.ready) {
      message.success("后端预检通过");
    } else {
      message.error(report.error || "后端预检失败");
    }
  } catch (error) {
    message.error(String(error || "后端预检失败"));
  } finally {
    backendPreflightRunning.value = false;
  }
}

async function openDebugPanel() {
  try {
    await openPanel();
  } catch (error) {
    message.error(String(error || "打开调试面板失败"));
  }
}
</script>

<template>
  <n-space align="center" wrap>
    <n-button
      v-if="!store.isRunning"
      type="success"
      @click="startWithValidation"
    >
      <template #icon><IconPlayerPlay /></template>
      启动
    </n-button>

    <n-button
      v-if="store.isRunning"
      type="error"
      @click="stopEngine"
    >
      <template #icon><IconPlayerStop /></template>
      停止
    </n-button>

    <n-button size="small" :loading="backendPreflightRunning" @click="runBackendPreflight">
      <template #icon><IconRefresh /></template>
      后端预检
    </n-button>
    <n-button size="small" secondary @click="openDebugPanel">
      <template #icon><IconBug /></template>
      调试面板
    </n-button>

    <n-tag v-if="store.isRunning" type="success" size="small">运行中</n-tag>
    <n-tag v-else type="default" size="small">已停止</n-tag>

    <n-tag
      v-if="backendPreflight || backendPreflightSkipped"
      :type="backendPreflightTagType"
      size="small"
    >
      后端预检：{{ backendPreflightStatus }}
    </n-tag>

    <span v-if="store.isRunning" class="text-xs text-gray-400">
      Phase {{ store.currentPhase + 1 }} · 循环 {{ store.cycleCount }}
    </span>
    <span
      v-if="store.isRunning && castBarRoiDetail"
      class="max-w-[360px] truncate text-xs text-gray-400"
      :title="castBarRoiDetail"
    >
      {{ castBarRoiDetail }}
    </span>
    <span
      v-if="backendPreflight || backendPreflightSkipped"
      class="max-w-[280px] truncate text-xs text-gray-400"
      :title="backendPreflightDetail"
    >
      {{ backendPreflightDetail }}
    </span>
  </n-space>
</template>
