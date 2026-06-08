<script setup lang="ts">
import { ref, h } from "vue";
import { NCard, NButton, NSpace, NDataTable, NTag } from "naive-ui";
import { IconPlayerPlay } from "@tabler/icons-vue";
import { useEngine } from "../composables/useEngine";
import type { DataTableColumns } from "naive-ui";

interface SimEvent {
  index: number;
  timeMs: number;
  phase: string;
  skillId: string;
  skillName: string;
  outcome: string;
  castMs: number;
  cdMs: number;
  reason: string;
}

const events = ref<SimEvent[]>([]);
const running = ref(false);
const { simulateRotation } = useEngine();

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
  { title: "技能", key: "skillName", width: 80 },
  {
    title: "结果", key: "outcome", width: 60,
    render: (row) =>
      row.outcome === "Success"
        ? h(NTag, { type: "success", size: "small" }, { default: () => "成功" })
        : h(NTag, { type: "warning", size: "small" }, { default: () => row.outcome }),
  },
  {
    title: "耗时", key: "castMs", width: 80,
    render: (row) => (row.castMs > 0 ? `读条${row.castMs}ms` : "即时"),
  },
  {
    title: "冷却", key: "cdMs", width: 80,
    render: (row) => (row.cdMs > 0 ? `${row.cdMs / 1000}s` : "—"),
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
      label: e.skillName || e.skillId,
      timeLabel: `${(e.timeMs / 1000).toFixed(1)}s`,
    });
    prevEnd = e.timeMs + dur;
  }
  timelineBars.value = bars;
  timelineContainerMinWidth.value = Math.max(TIMELINE_PX, bars.length * 60) + "px";
}

async function runSim() {
  running.value = true;
  events.value = [];
  try {
    const result = await simulateRotation();
    events.value = result.events || [];
    buildTimeline(events.value);
  } catch (e) {
    console.error("推演失败:", e);
  }
  running.value = false;
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">离线推演</h1>
      <n-space>
        <n-button type="primary" size="small" :loading="running" @click="runSim">
          <template #icon><IconPlayerPlay /></template>
          运行推演
        </n-button>
      </n-space>
    </div>

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
