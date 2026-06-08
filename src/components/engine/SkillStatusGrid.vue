<script setup lang="ts">
import { NDataTable, NTag } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { computed, h } from "vue";
import { useEngineStore } from "../../stores/engine";
import type { SkillRuntimeState } from "../../types/engine";

const store = useEngineStore();

interface SkillRow {
  skillId: string;
  skillName: string;
  state: string;
  attemptStarted: number;
  success: number;
  fail: number;
  readyFalse: number;
}

const columns: DataTableColumns<SkillRow> = [
  {
    title: "Skill",
    key: "skillName",
    ellipsis: { tooltip: true },
    render: (row) => row.skillName || row.skillId,
  },
  {
    title: "State",
    key: "state",
    width: 130,
    render: (row) => {
      const color =
        row.state === "SUCCESS"
          ? "success"
          : row.state === "FAILED"
            ? "error"
            : row.state === "CASTING"
              ? "info"
              : "default";
      return h(NTag, { type: color, size: "small" }, { default: () => row.state });
    },
  },
  { title: "Attempts", key: "attemptStarted", width: 100 },
  { title: "Success", key: "success", width: 90 },
  { title: "Fail", key: "fail", width: 80 },
  { title: "Not Ready", key: "readyFalse", width: 100 },
];

const rows = computed<SkillRow[]>(() =>
  store.skillRows.map((skill: SkillRuntimeState) => ({
    skillId: skill.skillId,
    skillName: skill.skillName,
    state: skill.state,
    attemptStarted: skill.attemptStarted,
    success: skill.success,
    fail: skill.fail,
    readyFalse: skill.readyFalse,
  }))
);
</script>

<template>
  <n-data-table
    :columns="columns"
    :data="rows"
    :bordered="false"
    size="small"
    :max-height="260"
  />
</template>
