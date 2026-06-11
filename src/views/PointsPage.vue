<script setup lang="ts">
import { ref, onMounted, onUnmounted, h } from "vue";
import { NCard, NButton, NSpace, NDataTable, NInput, NInputNumber, NTag, useMessage } from "naive-ui";
import { IconTrash, IconDeviceFloppy, IconPointer, IconRefresh } from "@tabler/icons-vue";
import { useCapture, type CaptureDiagnosticsResult } from "../composables/useCapture";
import {
  useProfile,
  withProfilePoints,
} from "../composables/useProfile";
import {
  firstPointDraftError,
  normalizePointDraft,
  validatePointDraft,
} from "../utils/point-validation";
import { firstProfileError, validateProfileForSave } from "../utils/profile-validation";
import type { DataTableColumns } from "naive-ui";
import type { Point } from "../types/point";

const points = ref<Point[]>([]);
const picking = ref(false);
const diagnosticsRunning = ref(false);
const diagnostics = ref<CaptureDiagnosticsResult | null>(null);
const diagnosticsStatus = ref<"idle" | "passed" | "failed" | "skipped">("idle");
const diagnosticsMessage = ref("");
const lastCapture = ref(0);
const { captureAtCursor, captureDiagnostics, store: pickerStore } = useCapture();
const { loadActiveProfile, saveActiveProfile } = useProfile();
const message = useMessage();

function hasTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as Window & { __TAURI_INTERNALS__?: unknown })
  );
}

function diagnosticsTagType(): "success" | "error" | "warning" | "default" {
  if (diagnosticsStatus.value === "passed") return "success";
  if (diagnosticsStatus.value === "failed") return "error";
  if (diagnosticsStatus.value === "skipped") return "warning";
  return "default";
}

function diagnosticsStatusLabel(): string {
  const labels = {
    idle: "未运行",
    passed: "通过",
    failed: "失败",
    skipped: "跳过",
  };
  return labels[diagnosticsStatus.value];
}

// F8 快捷键取色 — 仅在取色模式下生效
async function captureNow() {
  if (!picking.value) {
    pickerStore.recordCaptureIgnored("points", "not picking");
    return;
  }
  const now = Date.now();
  if (now - lastCapture.value < 400) {
    pickerStore.recordCaptureIgnored("points", "debounced");
    return;
  }
  lastCapture.value = now;
  pickerStore.recordCaptureRequest("points");
  try {
    const result = await captureAtCursor();
    if (!result) {
      pickerStore.recordCaptureFailure("points", "capture_at_cursor returned empty result");
      return;
    }
    const draft = normalizePointDraft({
      id: String(Date.now()),
      name: `(${result.x},${result.y})`,
      monitor: result.monitor, vx: result.x, vy: result.y,
      color: { r: result.r, g: result.g, b: result.b },
      tolerance: 20,
      sample: { mode: "single", radius: 0 },
      captured_at: new Date().toISOString(),
      note: result.hex,
    });
    const error = validatePointDraft(draft, {
      existingPoints: points.value,
      editingIndex: -1,
    });
    if (error) {
      pickerStore.recordCaptureFailure("points", error);
      message.error(error);
      return;
    }
    points.value.push(draft);
    pickerStore.recordCaptureSuccess("points", `${result.monitor} (${result.x},${result.y}) ${result.hex}`);
    message.success("已记录当前鼠标位置点位");
  } catch (e) {
    pickerStore.recordCaptureFailure("points", String(e || "capture failed"));
    message.error("取色失败，请确认屏幕捕获权限和鼠标位置");
  }
}

function startPicking() {
  picking.value = true;
  window.addEventListener("picker:capture", captureNow);
}

function stopPicking() {
  picking.value = false;
  window.removeEventListener("picker:capture", captureNow);
}

function togglePicking() {
  if (picking.value) stopPicking();
  else startPicking();
}

async function runCaptureDiagnostics() {
  diagnosticsRunning.value = true;
  diagnostics.value = null;
  diagnosticsMessage.value = "";
  try {
    if (!hasTauriRuntime()) {
      diagnosticsStatus.value = "skipped";
      diagnosticsMessage.value = "Tauri IPC runtime unavailable";
      message.warning("取色诊断已跳过：当前不是 Tauri 运行环境");
      return;
    }

    const result = await captureDiagnostics();
    diagnostics.value = result;
    if (!result) {
      diagnosticsStatus.value = "failed";
      diagnosticsMessage.value = "capture_diagnostics returned empty result";
      message.error("取色诊断失败");
      return;
    }

    if (result.sample) {
      diagnosticsStatus.value = "passed";
      diagnosticsMessage.value = `${result.cursor_monitor} (${result.cursor_x},${result.cursor_y}) ${result.sample.hex}`;
      message.success("取色诊断通过");
    } else {
      diagnosticsStatus.value = "failed";
      diagnosticsMessage.value = result.sample_error || "sample failed";
      message.error("取色诊断失败");
    }
  } finally {
    diagnosticsRunning.value = false;
  }
}

const columns: DataTableColumns<Point> = [
  {
    title: "ID", key: "id", width: 150,
    ellipsis: { tooltip: true },
    render: (row: Point, index: number) =>
      h(NInput, { size: "tiny", value: row.id, onUpdateValue: (v: string) => { points.value[index].id = v; } }),
  },
  {
    title: "名称", key: "name", width: 130,
    render: (row: Point, index: number) =>
      h(NInput, { size: "tiny", value: row.name, onUpdateValue: (v: string) => { points.value[index].name = v; } }),
  },
  {
    title: "位置", key: "vx", width: 100,
    render: (row: Point) => `${row.vx}, ${row.vy}`,
  },
  {
    title: "显示器", key: "monitor", width: 150,
    ellipsis: { tooltip: true },
    render: (row: Point) => row.monitor || "primary",
  },
  {
    title: "颜色", key: "color", width: 120,
    render: (row: Point) =>
      h("div", { class: "flex items-center gap-1" }, [
        h("div", {
          class: "w-4 h-4 rounded border border-white/20",
          style: { backgroundColor: `rgb(${row.color.r},${row.color.g},${row.color.b})` },
        }),
        h("span", { class: "text-xs" },
          `#${row.color.r.toString(16).padStart(2, "0")}${row.color.g.toString(16).padStart(2, "0")}${row.color.b.toString(16).padStart(2, "0")}`),
      ]),
  },
  {
    title: "容差", key: "tolerance", width: 96,
    render: (row: Point, index: number) =>
      h(NInputNumber, {
        size: "tiny",
        value: row.tolerance,
        min: 0,
        max: 255,
        precision: 0,
        onUpdateValue: (v: number | null) => { points.value[index].tolerance = v ?? 0; },
      }),
  },
  {
    title: "操作", key: "actions", width: 60,
    render: (_row: Point, index: number) =>
      h(NButton, { size: "tiny", quaternary: true, type: "error", onClick: () => { points.value.splice(index, 1); } },
        { icon: () => h(IconTrash) }),
  },
];

async function loadPoints() {
  try {
    const profile = await loadActiveProfile();
    points.value = profile.points.points;
  } catch (e) {
    points.value = [];
    message.error(String(e || "加载点位配置失败"));
  }
}

async function savePoints() {
  try {
    const draftError = firstPointDraftError(points.value);
    if (draftError) {
      message.error(draftError);
      return;
    }
    const normalizedPoints = points.value.map(normalizePointDraft);
    const profile = await loadActiveProfile();
    const next = withProfilePoints(profile, JSON.parse(JSON.stringify(normalizedPoints)) as Point[]);
    const error = firstProfileError(validateProfileForSave(next));
    if (error) {
      message.error(error);
      return;
    }
    await saveActiveProfile(next);
    points.value = normalizedPoints;
    message.success("点位配置已保存");
  } catch (e) {
    message.error("保存点位失败");
  }
}

function onActiveProfileChanged() {
  void loadPoints();
}

onMounted(() => {
  window.addEventListener("profile:active-changed", onActiveProfileChanged);
  void loadPoints();
});
onUnmounted(() => {
  window.removeEventListener("profile:active-changed", onActiveProfileChanged);
  stopPicking();
});
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">点位管理</h1>
      <n-space>
        <n-button size="small" :loading="diagnosticsRunning" @click="runCaptureDiagnostics">
          <template #icon><IconRefresh /></template>
          取色诊断
        </n-button>
        <n-button size="small" @click="savePoints"><template #icon><IconDeviceFloppy /></template>保存</n-button>
        <n-button
          size="small"
          :type="picking ? 'error' : 'primary'"
          @click="togglePicking"
        >
          <template #icon><IconPointer /></template>
          {{ picking ? '停止取色 (F8)' : '开始取色' }}
        </n-button>
      </n-space>
    </div>
    <n-card v-if="diagnosticsStatus !== 'idle'" size="small" title="取色诊断" class="mb-4">
      <div class="grid grid-cols-1 gap-2 text-sm md:grid-cols-[96px_minmax(0,1fr)]">
        <div class="text-gray-400">状态</div>
        <div class="flex items-center gap-2">
          <n-tag :type="diagnosticsTagType()" size="small">{{ diagnosticsStatusLabel() }}</n-tag>
          <span class="truncate text-xs text-gray-400" :title="diagnosticsMessage">{{ diagnosticsMessage }}</span>
        </div>
        <template v-if="diagnostics">
          <div class="text-gray-400">显示器</div>
          <div class="text-gray-200">
            {{ diagnostics.monitor_count }} 个 · {{ diagnostics.monitors.join(', ') || '无' }}
          </div>
          <div class="text-gray-400">鼠标</div>
          <div class="text-gray-200">
            {{ diagnostics.cursor_monitor }} · {{ diagnostics.cursor_x }}, {{ diagnostics.cursor_y }}
          </div>
          <div class="text-gray-400">采样</div>
          <div class="flex items-center gap-2 text-gray-200">
            <span v-if="diagnostics.sample">{{ diagnostics.sample.hex }}</span>
            <span v-else>{{ diagnostics.sample_error || '无采样结果' }}</span>
            <span
              v-if="diagnostics.sample"
              class="inline-block h-4 w-4 rounded border border-white/20"
              :style="{ backgroundColor: diagnostics.sample.hex }"
            />
          </div>
        </template>
      </div>
    </n-card>
    <n-card>
      <n-data-table :columns="columns" :data="points" :bordered="false" size="small" :max-height="500" virtual-scroll />
      <div v-if="picking" class="text-xs text-green-400 mt-2">
        ● 取色中 — 鼠标移动到目标位置，按 F8 记录点位
      </div>
      <div
        v-if="picking || pickerStore.captureRequestCount > 0 || pickerStore.captureIgnoredCount > 0"
        class="mt-2 grid grid-cols-1 gap-2 rounded border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-gray-300 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      >
        <div>
          取色处理：请求 {{ pickerStore.captureRequestCount }} · 成功 {{ pickerStore.captureSuccessCount }} · 失败 {{ pickerStore.captureFailureCount }} · 忽略 {{ pickerStore.captureIgnoredCount }}
        </div>
        <div class="truncate text-gray-400" :title="pickerStore.lastCaptureMessage">
          最近：{{ pickerStore.lastCaptureStatus }} · {{ pickerStore.lastCaptureContext || '无' }} · {{ pickerStore.lastCaptureMessage || '无' }}
        </div>
      </div>
    </n-card>
  </div>
</template>
