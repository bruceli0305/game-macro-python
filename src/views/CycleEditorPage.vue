<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { NButton, NSpace, NDivider } from "naive-ui";
import { IconPlus, IconDeviceFloppy } from "@tabler/icons-vue";
import PhaseLane from "../components/editor/PhaseLane.vue";
import SkillEditModal from "../components/editor/SkillEditModal.vue";
import EngineControlBar from "../components/engine/EngineControlBar.vue";
import ExecLogViewer from "../components/engine/ExecLogViewer.vue";
import SkillStatusGrid from "../components/engine/SkillStatusGrid.vue";
import { DEFAULT_PROFILE_NAME, useProfile } from "../composables/useProfile";
import { useEngineStore } from "../stores/engine";
import type { CycleConfig, SkillSlot } from "../types/cycle";
import type { Skill } from "../types/skill";

const engineStore = useEngineStore();
const { loadOrCreateProfile, saveRotations } = useProfile();

const defaultConfig: CycleConfig = {
  name: "我的循环", phases: [{ name: "", skills: [], complete_when: "any_fired" }],
  poll_interval_ms: 100, max_cycles: 0,
};
const config = reactive<CycleConfig>(JSON.parse(JSON.stringify(defaultConfig)));

const savedSkills = ref<Skill[]>([]);
const skillList = ref<{ id: string; name: string }[]>([]);
const collapsedPhases = ref<Set<number>>(new Set());

// 编辑弹窗状态
const showEditModal = ref(false);
const editingSlot = reactive<SkillSlot>({
  skill_id: "",
  priority: 1,
  label: "",
  condition_expr: null,
  start_expr: null,
  complete_expr: null,
  override_cast_ms: null,
});
const editingPhaseIdx = ref(-1);
const editingSlotIdx = ref(-1);

const skillNames = ref<Record<string, string>>({});

onMounted(async () => {
  try {
    const p = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    if (p?.rotations?.length > 0) Object.assign(config, p.rotations[0]);
    savedSkills.value = p?.skills?.skills || [];
    skillList.value = savedSkills.value.map((s) => ({ id: s.id, name: s.name || s.id }));
    skillNames.value = Object.fromEntries(savedSkills.value.map((s) => [s.id, s.name || s.id]));
  } catch { /* 首次 */ }
});

function addPhase() { config.phases.push({ name: "", skills: [], complete_when: "any_fired" }); }
function removePhase(i: number) { config.phases.splice(i, 1); }
function addSlot(pi: number) {
  config.phases[pi].skills.push({
    skill_id: "",
    priority: config.phases[pi].skills.length + 1,
    label: "",
    condition_expr: null,
    start_expr: null,
    complete_expr: null,
    override_cast_ms: null,
  });
}
function removeSlot(pi: number, si: number) { config.phases[pi].skills.splice(si, 1); }

function openEdit(pi: number, si: number) {
  editingPhaseIdx.value = pi;
  editingSlotIdx.value = si;
  Object.assign(editingSlot, JSON.parse(JSON.stringify(config.phases[pi].skills[si])));
  showEditModal.value = true;
}
function onSaved(slot: SkillSlot) {
  if (editingPhaseIdx.value >= 0 && editingSlotIdx.value >= 0) {
    config.phases[editingPhaseIdx.value].skills[editingSlotIdx.value] = slot;
  }
}
function toggleCollapse(i: number) {
  if (collapsedPhases.value.has(i)) collapsedPhases.value.delete(i);
  else collapsedPhases.value.add(i);
}

async function saveProfile() {
  try {
    await saveRotations(DEFAULT_PROFILE_NAME, [JSON.parse(JSON.stringify(config)) as CycleConfig]);
  } catch (e) { console.error(e); }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">循环编辑器</h1>
      <n-space>
        <n-button size="small" @click="saveProfile"><template #icon><IconDeviceFloppy /></template>保存</n-button>
        <n-button size="small" type="primary" @click="addPhase"><template #icon><IconPlus /></template>添加阶段</n-button>
      </n-space>
    </div>

    <EngineControlBar />
    <n-divider />

    <!-- Phase 泳道列表 -->
    <div class="space-y-2">
      <template v-for="(phase, pi) in config.phases" :key="pi">
        <PhaseLane
          :phase="phase"
          :phase-index="pi"
          :skill-names="skillNames"
          :collapsed="collapsedPhases.has(pi)"
          :style="engineStore.isRunning && engineStore.currentPhase === pi
            ? 'border-color: #18a058; box-shadow: 0 0 8px rgba(24,160,88,0.3)'
            : ''"
          @update:phase="(p: any) => config.phases[pi] = p"
          @remove="removePhase(pi)"
          @add-slot="addSlot(pi)"
          @edit-slot="(si: number) => openEdit(pi, si)"
          @remove-slot="(si: number) => removeSlot(pi, si)"
          @toggle-collapse="toggleCollapse(pi)"
        />
        <!-- Phase 间箭头 -->
        <div v-if="pi < config.phases.length - 1" class="flex justify-center">
          <span class="text-gray-600 text-lg leading-none">↓</span>
        </div>
      </template>
    </div>

    <n-divider />
    <SkillStatusGrid />
    <n-divider />
    <ExecLogViewer />

    <!-- 编辑弹窗 -->
    <SkillEditModal
      :show="showEditModal"
      :slot="editingSlot"
      :skill-options="skillList"
      :point-options="[]"
      @update:show="showEditModal = $event"
      @saved="onSaved"
    />
  </div>
</template>
