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

function reasonLabel(reason: string): string {
  if (!reason) return "";
  if (reason.startsWith("cooldown_until=")) return `冷却中 (${reason})`;
  if (reason.startsWith("shots_per_cycle_exhausted=")) return `本轮次数已用完 (${reason})`;
  const labels: Record<string, string> = {
    no_condition: "无条件",
    condition_true: "条件满足",
    skill_id_empty: "技能 ID 为空",
    skill_missing: "技能不存在",
    skill_disabled: "技能已禁用",
    ammo_unavailable: "弹药不可用",
    success: "成功",
    hybrid_assume_no_expr: "无完成信号，按读条成功",
    hybrid_assume_timeout: "完成信号超时，按策略成功",
    timeout: "超时",
    no_cast_start: "未检测到施法开始",
    send_key_failed: "发键失败",
    send_key_failed_retry: "重试发键失败",
  };
  return labels[reason] ? `${labels[reason]} (${reason})` : reason;
}

const logText = computed(() =>
  store.execLog
    .map(
      (e) =>
        `[${formatTime(e.tsMs)}] [${e.phaseName}] ${e.outcome} ${e.skillName || e.skillId}${e.reason ? ` - ${reasonLabel(e.reason)}` : ""}`
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
