<script setup lang="ts">
import { ref, onMounted, onUnmounted, h } from "vue";
import { NCard, NButton, NSpace, NDataTable, NInput } from "naive-ui";
import { IconTrash, IconDeviceFloppy, IconPointer } from "@tabler/icons-vue";
import { useCapture } from "../composables/useCapture";
import { DEFAULT_PROFILE_NAME, useProfile } from "../composables/useProfile";
import type { DataTableColumns } from "naive-ui";
import type { Point } from "../types/point";

const points = ref<Point[]>([]);
const picking = ref(false);
const lastCapture = ref(0);
const { captureAtCursor } = useCapture();
const { loadOrCreateProfile, savePoints: persistProfilePoints } = useProfile();

// F8 快捷键取色 — 仅在取色模式下生效
async function captureNow() {
  if (!picking.value) return;
  const now = Date.now();
  if (now - lastCapture.value < 400) return;
  lastCapture.value = now;
  try {
    const result = await captureAtCursor();
    if (!result) return;
    points.value.push({
      id: String(Date.now()),
      name: `(${result.x},${result.y})`,
      monitor: "primary", vx: result.x, vy: result.y,
      color: { r: result.r, g: result.g, b: result.b },
      tolerance: 20,
      sample: { mode: "single", radius: 0 },
      captured_at: new Date().toISOString(),
      note: result.hex,
    });
  } catch (e) { console.error("取色失败:", e); }
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

const columns: DataTableColumns<Point> = [
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
    title: "操作", key: "actions", width: 60,
    render: (_row: Point, index: number) =>
      h(NButton, { size: "tiny", quaternary: true, type: "error", onClick: () => { points.value.splice(index, 1); } },
        { icon: () => h(IconTrash) }),
  },
];

async function loadPoints() {
  try {
    const profile = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    points.value = profile.points.points;
  } catch { /* 首次使用 */ }
}

async function savePoints() {
  try {
    await persistProfilePoints(DEFAULT_PROFILE_NAME, points.value);
  } catch (e) { console.error(e); }
}

onMounted(() => loadPoints());
onUnmounted(() => stopPicking());
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">点位管理</h1>
      <n-space>
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
    <n-card>
      <n-data-table :columns="columns" :data="points" :bordered="false" size="small" :max-height="500" virtual-scroll />
      <div v-if="picking" class="text-xs text-green-400 mt-2">
        ● 取色中 — 鼠标移动到目标位置，按 F8 记录点位
      </div>
    </n-card>
  </div>
</template>
