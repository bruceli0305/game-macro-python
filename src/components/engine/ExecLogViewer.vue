<script setup lang="ts">
import { NLog } from "naive-ui";
import { computed } from "vue";
import { useEngineStore } from "../../stores/engine";

const store = useEngineStore();

function formatTime(ms: number): string {
  if (ms < 1000) return `+${ms}ms`;
  const s = (ms / 1000).toFixed(1);
  return `+${s}s`;
}

const logText = computed(() =>
  store.execLog
    .map(
      (e) =>
        `[${formatTime(e.tsMs)}] [${e.phaseName}] ${e.outcome} ${e.skillName || e.skillId}${e.reason ? ` — ${e.reason}` : ""}`
    )
    .join("\n")
);
</script>

<template>
  <n-log
    :log="logText"
    :rows="10"
    language="naive-log"
    :trim="false"
  />
</template>
