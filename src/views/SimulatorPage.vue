<script setup lang="ts">
import { computed, onMounted, ref, h } from "vue";
import { NCard, NButton, NSpace, NDataTable, NTag, NSwitch, useMessage } from "naive-ui";
import { IconCopy, IconPlayerPlay, IconRefresh, IconTrash } from "@tabler/icons-vue";
import ProfileIssueSummary from "../components/common/ProfileIssueSummary.vue";
import { useCapture } from "../composables/useCapture";
import { useEngine, type PixelOverride } from "../composables/useEngine";
import { useHotkeys } from "../composables/useHotkeys";
import { DEFAULT_PROFILE_NAME, useProfile } from "../composables/useProfile";
import {
  ipcSmokeDebugJson,
  runDesktopIpcSmoke,
  type IpcSmokeStep,
  type IpcSmokeStatus,
} from "../utils/desktop-ipc-smoke";
import { createIpcSmokeProfile } from "../utils/ipc-smoke-profile";
import { firstProfileError, validateProfileForRun } from "../utils/profile-validation";
import {
  simulationDebugJson,
  simulationEventLabel,
  simulationOutcomeLabel,
  simulationOutcomeTagType,
  simulationReasonLabel,
  summarizeSimulation,
} from "../utils/simulation-debug";
import type { DataTableColumns } from "naive-ui";
import type { PixelSpec } from "../types/skill";
import type { Profile } from "../types/profile";

interface SimEvent {
  index: number;
  timeMs: number;
  phase: string;
  event: string;
  skillId: string;
  skillName: string;
  outcome: string;
  castMs: number;
  cdMs: number;
  reason: string;
}

const events = ref<SimEvent[]>([]);
const running = ref(false);
const ipcSmokeRunning = ref(false);
const ipcSmokeSteps = ref<IpcSmokeStep[]>([]);
const simulatedPixels = ref(false);
const profile = ref<Profile | null>(null);
const pointMatches = ref<Record<string, boolean>>({});
const skillMatches = ref<Record<string, boolean>>({});
const ammoMatches = ref<Record<string, boolean>>({});
const {
  preflight,
  simulateRotation,
  simulateRotationWithPixels,
  simulateProfileRotation,
  simulateProfileRotationWithPixels,
  simulateIpcSmokeFixture,
} = useEngine();
const { loadOrCreateProfile } = useProfile();
const { captureDiagnostics } = useCapture();
const { diagnostics: hotkeyDiagnostics } = useHotkeys();
const message = useMessage();

const pointRows = computed(() => profile.value?.points.points || []);
const skillRows = computed(() => profile.value?.skills.skills || []);
const ammoRows = computed(() =>
  skillRows.value.flatMap((skill) =>
    skill.ammo_stages.map((stage, index) => ({
      key: `${skill.id}:${index}`,
      skillName: skill.name || skill.id,
      chargesLeft: stage.charges_left,
      pixel: stage.pixel,
    }))
  )
);
const summary = computed(() => summarizeSimulation(events.value));
const canCopyDebug = computed(() => events.value.length > 0 && !running.value);
const canCopyIpcSmoke = computed(() => ipcSmokeSteps.value.length > 0 && !ipcSmokeRunning.value);
const runIssues = computed(() => profile.value ? validateProfileForRun(profile.value) : []);
const hasIpcSmokeSteps = computed(() => ipcSmokeSteps.value.length > 0);

const columns: DataTableColumns<SimEvent> = [
  { title: "#", key: "index", width: 40 },
  {
    title: "时间", key: "timeMs", width: 90,
    render: (row) => {
      const s = (row.timeMs / 1000).toFixed(1);
      return `${s}s`;
    },
  },
  { title: "阶段", key: "phase", width: 80 },
  {
    title: "事件", key: "event", width: 96,
    render: (row) => simulationEventLabel(row.event),
  },
  { title: "技能", key: "skillName", width: 80 },
  {
    title: "结果", key: "outcome", width: 76,
    render: (row) =>
      h(
        NTag,
        { type: simulationOutcomeTagType(row.outcome), size: "small" },
        { default: () => simulationOutcomeLabel(row.outcome) }
      ),
  },
  {
    title: "耗时", key: "castMs", width: 80,
    render: (row) => (row.castMs > 0 ? `读条${row.castMs}ms` : "即时"),
  },
  {
    title: "冷却", key: "cdMs", width: 80,
    render: (row) => (row.cdMs > 0 ? `${row.cdMs / 1000}s` : "—"),
  },
  {
    title: "原因",
    key: "reason",
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: (row) => simulationReasonLabel(row.reason),
  },
];

// 时间线数据 — 使用 px 宽度，基于 1200px 总宽
const TIMELINE_PX = 1200;
const maxTime = ref(0);
const timelineBars = ref<{ gapPx: number; barPx: number; color: string; label: string; timeLabel: string }[]>([]);
const timelineContainerMinWidth = ref("1200px");

function buildTimeline(evts: SimEvent[]) {
  if (evts.length === 0) return;
  const totalMs = Math.max(evts[evts.length - 1].timeMs + (evts[evts.length - 1].castMs || 1000), 1000);
  maxTime.value = totalMs;
  const scale = TIMELINE_PX / totalMs;
  const colors = ["#18a058", "#2080f0", "#f0a020", "#d03050", "#7c3aed"];
  const bars: typeof timelineBars.value = [];

  let prevEnd = 0;
  for (const e of evts) {
    const gap = e.timeMs - prevEnd;
    const dur = Math.max(e.castMs || 0, 200);
    const colorIdx = (e.phase.charCodeAt(e.phase.length - 1) || 0) % colors.length;
    bars.push({
      gapPx: Math.max(gap > 0 ? gap * scale : 0, 0),
      barPx: Math.max(dur * scale, 40),
      color: colors[colorIdx],
      label: e.skillName || e.skillId || simulationEventLabel(e.event),
      timeLabel: `${(e.timeMs / 1000).toFixed(1)}s`,
    });
    prevEnd = e.timeMs + dur;
  }
  timelineBars.value = bars;
  timelineContainerMinWidth.value = Math.max(TIMELINE_PX, bars.length * 60) + "px";
}

function mismatchColor(pixel: PixelSpec): [number, number, number] {
  return [
    (pixel.color.r + 128) % 256,
    (pixel.color.g + 128) % 256,
    (pixel.color.b + 128) % 256,
  ];
}

function overrideFromPixel(pixel: PixelSpec, matched: boolean): PixelOverride {
  const [r, g, b] = matched
    ? [pixel.color.r, pixel.color.g, pixel.color.b]
    : mismatchColor(pixel);
  return {
    monitor: pixel.monitor,
    x: pixel.vx,
    y: pixel.vy,
    r,
    g,
    b,
  };
}

function buildPixelOverrides(current: Profile): PixelOverride[] {
  const overrides: PixelOverride[] = [];
  for (const point of current.points.points) {
    overrides.push(
      overrideFromPixel(
        {
          monitor: point.monitor,
          vx: point.vx,
          vy: point.vy,
          color: point.color,
          tolerance: point.tolerance,
          sample: point.sample,
        },
        pointMatches.value[point.id] ?? true
      )
    );
  }

  for (const skill of current.skills.skills) {
    overrides.push(overrideFromPixel(skill.pixel, skillMatches.value[skill.id] ?? true));
    skill.ammo_stages.forEach((stage, index) => {
      overrides.push(
        overrideFromPixel(stage.pixel, ammoMatches.value[`${skill.id}:${index}`] ?? true)
      );
    });
  }
  return overrides;
}

async function loadSimulatorProfile() {
  profile.value = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
  for (const point of profile.value.points.points) {
    pointMatches.value[point.id] ??= true;
  }
  for (const skill of profile.value.skills.skills) {
    skillMatches.value[skill.id] ??= true;
    skill.ammo_stages.forEach((_stage, index) => {
      ammoMatches.value[`${skill.id}:${index}`] ??= true;
    });
  }
}

async function runSim() {
  running.value = true;
  events.value = [];
  try {
    const current = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    profile.value = current;
    const error = firstProfileError(validateProfileForRun(current));
    if (error) {
      message.error(error);
      return;
    }
    const result = simulatedPixels.value
      ? await simulateRotationWithPixels(buildPixelOverrides(current))
      : await simulateRotation();
    events.value = result.events || [];
    buildTimeline(events.value);
  } catch (e) {
    console.error("推演失败:", e);
    message.error(String(e || "推演失败"));
  } finally {
    running.value = false;
  }
}

async function loadProfileForIpcSmoke(): Promise<Profile> {
  await loadSimulatorProfile();
  if (!profile.value) {
    throw new Error("profile load returned empty state");
  }
  return profile.value;
}

function smokeStatusLabel(status: IpcSmokeStatus): string {
  const labels: Record<IpcSmokeStatus, string> = {
    passed: "通过",
    failed: "失败",
    skipped: "跳过",
  };
  return labels[status];
}

function smokeTagType(status: IpcSmokeStatus): "success" | "error" | "warning" {
  if (status === "passed") return "success";
  if (status === "failed") return "error";
  return "warning";
}

function hasTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as Window & { __TAURI_INTERNALS__?: unknown })
  );
}

async function runIpcSmoke() {
  ipcSmokeRunning.value = true;
  ipcSmokeSteps.value = [];
  try {
    const tauriRuntimeAvailable = hasTauriRuntime();
    const steps = await runDesktopIpcSmoke({
      loadProfile: loadProfileForIpcSmoke,
      simulateRotation,
      simulateRotationWithPixels,
      buildPixelOverrides,
      createSmokeProfile: createIpcSmokeProfile,
      simulateProfileRotation: tauriRuntimeAvailable ? simulateProfileRotation : undefined,
      simulateProfileRotationWithPixels: tauriRuntimeAvailable
        ? simulateProfileRotationWithPixels
        : undefined,
      simulateIpcSmokeFixture: tauriRuntimeAvailable ? simulateIpcSmokeFixture : undefined,
      enginePreflight: tauriRuntimeAvailable ? preflight : undefined,
      captureDiagnostics: tauriRuntimeAvailable ? captureDiagnostics : undefined,
      hotkeyDiagnostics: tauriRuntimeAvailable ? hotkeyDiagnostics : undefined,
    });
    ipcSmokeSteps.value = steps;

    const failed = steps.filter((step) => step.status === "failed").length;
    const skipped = steps.filter((step) => step.status === "skipped").length;
    if (failed > 0) {
      message.error(`IPC 自检失败 ${failed} 项`);
    } else if (skipped > 0) {
      message.warning(`IPC 自检跳过 ${skipped} 项`);
    } else {
      message.success("IPC 自检通过");
    }
  } catch (error) {
    const detail = String(error || "IPC smoke failed");
    ipcSmokeSteps.value = [
      {
        id: "ipc_smoke_unhandled",
        label: "IPC 自检",
        status: "failed",
        detail,
      },
    ];
    message.error(detail);
  } finally {
    ipcSmokeRunning.value = false;
  }
}

async function copyDebugJson() {
  if (!canCopyDebug.value) return;
  try {
    await navigator.clipboard.writeText(simulationDebugJson(events.value));
    message.success("推演调试 JSON 已复制");
  } catch (error) {
    console.error("copy simulation debug json failed:", error);
    message.error("复制失败，请检查剪贴板权限");
  }
}

async function copyIpcSmokeJson() {
  if (!canCopyIpcSmoke.value) return;
  try {
    await navigator.clipboard.writeText(ipcSmokeDebugJson(ipcSmokeSteps.value));
    message.success("IPC 自检 JSON 已复制");
  } catch (error) {
    console.error("copy IPC smoke json failed:", error);
    message.error("复制失败，请检查剪贴板权限");
  }
}

function clearResults() {
  events.value = [];
  timelineBars.value = [];
  maxTime.value = 0;
}

onMounted(() => {
  loadSimulatorProfile().catch((e) => {
    console.error("加载推演配置失败:", e);
  });
});
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">离线推演</h1>
      <n-space>
        <n-button size="small" :disabled="!canCopyDebug" @click="copyDebugJson">
          <template #icon><IconCopy /></template>
          复制调试 JSON
        </n-button>
        <n-button size="small" :disabled="events.length === 0 || running" @click="clearResults">
          <template #icon><IconTrash /></template>
          清空结果
        </n-button>
        <n-button size="small" :loading="ipcSmokeRunning" :disabled="running" @click="runIpcSmoke">
          <template #icon><IconRefresh /></template>
          IPC 自检
        </n-button>
        <n-button type="primary" size="small" :loading="running" @click="runSim">
          <template #icon><IconPlayerPlay /></template>
          运行推演
        </n-button>
      </n-space>
    </div>

    <ProfileIssueSummary
      :issues="runIssues"
      title="推演检查"
      :limit="5"
    />

    <n-card v-if="hasIpcSmokeSteps" size="small" title="IPC 自检" class="mb-4">
      <template #header-extra>
        <n-button size="tiny" :disabled="!canCopyIpcSmoke" @click="copyIpcSmokeJson">
          <template #icon><IconCopy /></template>
          复制 JSON
        </n-button>
      </template>
      <div class="space-y-2">
        <div
          v-for="step in ipcSmokeSteps"
          :key="step.id"
          class="grid grid-cols-1 gap-2 rounded border border-white/10 bg-white/[0.03] px-3 py-2 text-sm sm:grid-cols-[120px_64px_minmax(0,1fr)] sm:items-center sm:gap-3"
        >
          <span class="font-medium text-gray-100">{{ step.label }}</span>
          <n-tag :type="smokeTagType(step.status)" size="small">
            {{ smokeStatusLabel(step.status) }}
          </n-tag>
          <span class="truncate text-xs text-gray-400" :title="step.detail">{{ step.detail }}</span>
        </div>
      </div>
    </n-card>

    <n-card size="small" title="像素状态" class="mb-4">
      <div class="mb-3 flex items-center gap-3">
        <n-switch v-model:value="simulatedPixels" />
        <span class="text-sm text-gray-300">使用模拟像素状态</span>
      </div>

      <div v-if="simulatedPixels" class="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div>
          <div class="mb-2 text-xs font-semibold text-gray-400">点位</div>
          <div class="space-y-2">
            <div
              v-for="point in pointRows"
              :key="point.id"
              class="flex items-center justify-between rounded border border-white/10 px-3 py-2"
            >
              <span class="truncate text-xs text-gray-300">{{ point.name || point.id }}</span>
              <n-switch v-model:value="pointMatches[point.id]" size="small" />
            </div>
            <div v-if="pointRows.length === 0" class="text-xs text-gray-500">暂无点位</div>
          </div>
        </div>

        <div>
          <div class="mb-2 text-xs font-semibold text-gray-400">技能像素</div>
          <div class="space-y-2">
            <div
              v-for="skill in skillRows"
              :key="skill.id"
              class="flex items-center justify-between rounded border border-white/10 px-3 py-2"
            >
              <span class="truncate text-xs text-gray-300">{{ skill.name || skill.id }}</span>
              <n-switch v-model:value="skillMatches[skill.id]" size="small" />
            </div>
            <div v-if="skillRows.length === 0" class="text-xs text-gray-500">暂无技能</div>
          </div>
        </div>

        <div>
          <div class="mb-2 text-xs font-semibold text-gray-400">弹药阶段</div>
          <div class="space-y-2">
            <div
              v-for="ammo in ammoRows"
              :key="ammo.key"
              class="flex items-center justify-between rounded border border-white/10 px-3 py-2"
            >
              <span class="truncate text-xs text-gray-300">
                {{ ammo.skillName }} · 剩余 {{ ammo.chargesLeft }}
              </span>
              <n-switch v-model:value="ammoMatches[ammo.key]" size="small" />
            </div>
            <div v-if="ammoRows.length === 0" class="text-xs text-gray-500">暂无弹药阶段</div>
          </div>
        </div>
      </div>
    </n-card>

    <!-- 时间线 -->
    <n-card v-if="timelineBars.length > 0" size="small" title="时间线" class="mb-4">
      <div class="overflow-x-auto">
        <div class="flex flex-nowrap items-center bg-black/20 rounded p-1 h-8" :style="{ minWidth: timelineContainerMinWidth }">
          <template v-for="(bar, i) in timelineBars" :key="i">
            <!-- 间距 -->
            <div v-if="bar.gapPx > 1" class="flex-shrink-0" :style="{ width: bar.gapPx + 'px' }" />
            <!-- 技能条 -->
            <div
              class="flex-shrink-0 h-6 rounded flex items-center justify-center text-[11px] text-white font-semibold truncate px-1"
              :style="{ width: bar.barPx + 'px', backgroundColor: bar.color }"
              :title="`${bar.label} @ ${bar.timeLabel}`"
            >
              {{ bar.label }}
            </div>
          </template>
        </div>
      </div>
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>0s</span>
        <span>{{ (maxTime / 1000).toFixed(1) }}s</span>
      </div>
    </n-card>

    <n-card size="small">
      <div v-if="events.length > 0" class="mb-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4 xl:grid-cols-8">
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">事件</div>
          <div class="mt-1 text-base font-semibold text-gray-100">{{ summary.total }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">执行</div>
          <div class="mt-1 text-base font-semibold text-green-300">{{ summary.executed }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">跳过</div>
          <div class="mt-1 text-base font-semibold text-amber-300">{{ summary.skipped }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">跳转</div>
          <div class="mt-1 text-base font-semibold text-blue-300">{{ summary.transitions }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">成功</div>
          <div class="mt-1 text-base font-semibold text-green-300">{{ summary.success }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">未就绪</div>
          <div class="mt-1 text-base font-semibold text-amber-300">{{ summary.notReady }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">失败</div>
          <div class="mt-1 text-base font-semibold text-red-300">{{ summary.failed }}</div>
        </div>
        <div class="rounded border border-white/10 bg-white/[0.03] px-3 py-2">
          <div class="text-gray-500">耗时</div>
          <div class="mt-1 text-base font-semibold text-gray-100">{{ (summary.durationMs / 1000).toFixed(1) }}s</div>
        </div>
      </div>

      <div v-if="summary.topReasons.length > 0" class="mb-3 flex flex-wrap gap-2 text-xs">
        <n-tag
          v-for="item in summary.topReasons"
          :key="item.reason"
          size="small"
          type="info"
        >
          {{ simulationReasonLabel(item.reason) }} × {{ item.count }}
        </n-tag>
      </div>

      <n-data-table
        :columns="columns"
        :data="events"
        :bordered="false"
        size="small"
        :max-height="500"
        virtual-scroll
      />
      <div v-if="events.length === 0 && !running" class="text-sm text-gray-500 mt-4">
        点击"运行推演"查看模拟结果。请先在循环编辑器中保存配置。
      </div>
    </n-card>
  </div>
</template>
