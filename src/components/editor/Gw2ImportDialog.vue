<script setup lang="ts">
import { ref } from "vue";
import { NModal, NCard, NButton, NSpace, NInput, NDataTable, useMessage } from "naive-ui";
import { IconSearch, IconDownload } from "@tabler/icons-vue";
import { useSkill, type Gw2SkillInfo } from "../../composables/useSkill";
import type { DataTableColumns } from "naive-ui";

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{
  "update:show": [v: boolean];
  imported: [skills: Gw2SkillInfo[]];
}>();

const query = ref("");
const results = ref<Gw2SkillInfo[]>([]);
const selected = ref<number[]>([]);
const loading = ref(false);
const { searchGw2Skills } = useSkill();
const message = useMessage();

const columns: DataTableColumns<Gw2SkillInfo> = [
  { title: "ID", key: "id", width: 60 },
  { title: "名称", key: "name", width: 150 },
  {
    title: "冷却(ms)",
    key: "cooldown_ms",
    width: 80,
    render: (row) => (row.cooldown_ms > 0 ? String(row.cooldown_ms) : "—"),
  },
  {
    title: "半径",
    key: "radius",
    width: 60,
    render: (row) => (row.radius > 0 ? String(row.radius) : "—"),
  },
];

async function search() {
  loading.value = true;
  try {
    results.value = await searchGw2Skills(query.value);
  } catch (e) {
    message.error(String(e || "搜索失败"));
  }
  loading.value = false;
}

function toggleSelect(id: number) {
  const arr = selected.value;
  const idx = arr.indexOf(id);
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(id);
}

function importSelected() {
  const ids = new Set(selected.value);
  const imported = results.value.filter((s) => ids.has(s.id));
  emit("imported", imported);
  emit("update:show", false);
  selected.value = [];
  results.value = [];
  query.value = "";
}
</script>

<template>
  <n-modal :show="props.show" @update:show="(v) => emit('update:show', v)">
    <n-card
      title="导入 GW2 技能"
      style="width: 700px; max-height: 80vh"
      closable
      @close="emit('update:show', false)"
    >
      <n-space class="mb-4">
        <n-input
          v-model:value="query"
          placeholder="搜索技能名称..."
          style="width: 200px"
          @keyup.enter="search"
        />
        <n-button
          type="primary"
          size="small"
          :loading="loading"
          @click="search"
        >
          <template #icon><IconSearch /></template>
          搜索
        </n-button>
      </n-space>

      <n-data-table
        :columns="columns"
        :data="results"
        :bordered="false"
        size="small"
        :max-height="400"
        virtual-scroll
        :row-props="
          (row: Gw2SkillInfo) => ({
            style: selected.includes(row.id)
              ? 'background: rgba(24,160,88,0.15)'
              : '',
            onClick: () => toggleSelect(row.id),
          })
        "
      />

      <div class="text-xs text-gray-400 mt-2">
        点击行选择/取消，已选 {{ selected.length }} 个技能
      </div>

      <n-space justify="end" class="mt-4">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button
          type="primary"
          :disabled="selected.length === 0"
          @click="importSelected"
        >
          <template #icon><IconDownload /></template>
          导入已选
        </n-button>
      </n-space>
    </n-card>
  </n-modal>
</template>
