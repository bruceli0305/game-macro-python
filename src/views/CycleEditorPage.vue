<script setup lang="ts">
import { computed, reactive, ref, onMounted } from "vue";
import { NButton, NTag, useMessage } from "naive-ui";
import { IconPlus, IconDeviceFloppy } from "@tabler/icons-vue";
import PhaseLane from "../components/editor/PhaseLane.vue";
import SkillEditModal from "../components/editor/SkillEditModal.vue";
import ProfileIssueSummary from "../components/common/ProfileIssueSummary.vue";
import EngineControlBar from "../components/engine/EngineControlBar.vue";
import ExecLogViewer from "../components/engine/ExecLogViewer.vue";
import SkillStatusGrid from "../components/engine/SkillStatusGrid.vue";
import {
  DEFAULT_PROFILE_NAME,
  useProfile,
  withProfileRotations,
} from "../composables/useProfile";
import { useEngineStore } from "../stores/engine";
import {
  firstProfileError,
  validateProfileForEngineStart,
  validateProfileForSave,
} from "../utils/profile-validation";
import type { CycleConfig, SkillSlot } from "../types/cycle";
import type { Point } from "../types/point";
import type { Profile } from "../types/profile";
import type { Skill } from "../types/skill";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

const engineStore = useEngineStore();
const { loadOrCreateProfile, saveProfile: persistProfile } = useProfile();
const message = useMessage();

const defaultConfig: CycleConfig = {
  name: "我的循环", phases: [{ name: "", skills: [], complete_when: "any_fired" }],
  poll_interval_ms: 100, max_cycles: 0,
};
const config = reactive<CycleConfig>(JSON.parse(JSON.stringify(defaultConfig)));

const savedSkills = ref<Skill[]>([]);
const skillList = ref<{ id: string; name: string }[]>([]);
const savedPoints = ref<Point[]>([]);
const pointList = ref<{ id: string; name: string }[]>([]);
const collapsedPhases = ref<Set<number>>(new Set());
const loadedProfile = ref<Profile | null>(null);

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
const skillMeta = ref<Record<string, SkillCardMeta>>({});

const phaseCount = computed(() => config.phases.length);
const slotCount = computed(() =>
  config.phases.reduce((count, phase) => count + phase.skills.length, 0)
);
const engineStartIssues = computed(() => {
  if (!loadedProfile.value) return [];
  const next = withProfileRotations(
    loadedProfile.value,
    [JSON.parse(JSON.stringify(config)) as CycleConfig]
  );
  return validateProfileForEngineStart(next);
});

onMounted(async () => {
  try {
    const p = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    loadedProfile.value = p;
    if (p?.rotations?.length > 0) Object.assign(config, p.rotations[0]);
    savedSkills.value = p?.skills?.skills || [];
    skillList.value = savedSkills.value.map((s) => ({ id: s.id, name: s.name || s.id }));
    skillNames.value = Object.fromEntries(savedSkills.value.map((s) => [s.id, s.name || s.id]));
    skillMeta.value = Object.fromEntries(
      savedSkills.value.map((s) => [
        s.id,
        {
          triggerKey: s.trigger_key,
          readbarMs: s.cast.readbar_ms,
          cooldownMs: s.cooldown_ms || s.cast.cooldown_ms,
          shotsPerCycle: s.shots_per_cycle,
        },
      ]),
    );
    savedPoints.value = p?.points?.points || [];
    pointList.value = savedPoints.value.map((p) => ({ id: p.id, name: p.name || p.id }));
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
    const profile = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    const next = withProfileRotations(profile, [JSON.parse(JSON.stringify(config)) as CycleConfig]);
    const error = firstProfileError(validateProfileForSave(next));
    if (error) {
      message.error(error);
      return;
    }
    await persistProfile(DEFAULT_PROFILE_NAME, next);
    loadedProfile.value = next;
    message.success("循环配置已保存");
  } catch (e) {
    console.error(e);
    message.error("保存失败，请检查技能和点位引用");
  }
}
</script>

<template>
  <div class="cycle-editor-page flex h-full min-h-0 flex-col gap-4">
    <header class="cycle-editor-header flex flex-none flex-wrap items-center justify-between gap-3">
      <div class="cycle-editor-title min-w-0">
        <h1 class="text-xl font-bold leading-tight">循环编辑器</h1>
        <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-400">
          <n-tag size="small" :bordered="false">阶段 {{ phaseCount }}</n-tag>
          <n-tag size="small" :bordered="false">技能槽 {{ slotCount }}</n-tag>
          <span class="truncate">{{ config.name || "未命名循环" }}</span>
        </div>
      </div>
      <div class="cycle-editor-actions flex flex-wrap items-center gap-2">
        <n-button size="small" @click="saveProfile">
          <template #icon><IconDeviceFloppy /></template>
          保存
        </n-button>
        <n-button size="small" type="primary" @click="addPhase">
          <template #icon><IconPlus /></template>
          添加阶段
        </n-button>
      </div>
    </header>

    <div class="cycle-editor-grid grid min-h-0 flex-1 grid-cols-1 gap-4">
      <section class="cycle-editor-panel flex min-w-0 min-h-0 flex-col overflow-hidden rounded border border-white/10 bg-white/[0.02]">
        <div class="cycle-panel-header flex flex-none items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <h2 class="text-sm font-semibold text-gray-100">阶段编排</h2>
            <p class="mt-0.5 text-xs text-gray-500">按优先级从左到右编辑每个阶段的技能槽</p>
          </div>
        </div>

        <!-- Phase 泳道列表 -->
        <div class="cycle-phase-scroll min-h-0 flex-1 overflow-auto p-4">
          <div class="space-y-3">
            <template v-for="(phase, pi) in config.phases" :key="pi">
              <PhaseLane
                :phase="phase"
                :phase-index="pi"
                :skill-names="skillNames"
                :skill-meta="skillMeta"
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
        </div>
      </section>

      <aside class="cycle-monitor-panel grid min-w-0 grid-rows-[auto_minmax(220px,1fr)_220px] gap-4 overflow-hidden">
        <section class="cycle-side-section rounded border border-white/10 bg-white/[0.02] p-4">
          <h2 class="mb-3 text-sm font-semibold text-gray-100">运行控制</h2>
          <ProfileIssueSummary
            :issues="engineStartIssues"
            title="启动检查"
            :limit="4"
          />
          <EngineControlBar />
        </section>

        <section class="cycle-side-section cycle-side-fill flex min-h-0 flex-col overflow-hidden rounded border border-white/10 bg-white/[0.02]">
          <div class="cycle-side-header flex-none border-b border-white/10 px-4 py-3">
            <h2 class="text-sm font-semibold text-gray-100">技能状态</h2>
          </div>
          <div class="cycle-side-body min-h-0 flex-1 overflow-auto p-2">
            <SkillStatusGrid />
          </div>
        </section>

        <section class="cycle-side-section cycle-side-log flex min-h-0 flex-col overflow-hidden rounded border border-white/10 bg-white/[0.02]">
          <div class="cycle-side-header flex-none border-b border-white/10 px-4 py-3">
            <h2 class="text-sm font-semibold text-gray-100">执行日志</h2>
          </div>
          <div class="cycle-side-body min-h-0 flex-1 overflow-auto p-2">
            <ExecLogViewer />
          </div>
        </section>
      </aside>
    </div>

    <!-- 编辑弹窗 -->
    <SkillEditModal
      :show="showEditModal"
      :slot="editingSlot"
      :skill-options="skillList"
      :point-options="pointList"
      @update:show="showEditModal = $event"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.cycle-editor-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 16px;
}

.cycle-editor-header,
.cycle-editor-actions,
.cycle-panel-header {
  display: flex;
  align-items: center;
}

.cycle-editor-header {
  flex: 0 0 auto;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.cycle-editor-title {
  min-width: 0;
}

.cycle-editor-actions {
  gap: 8px;
  flex-wrap: wrap;
}

.cycle-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  flex: 1 1 auto;
  min-height: 0;
}

@media (min-width: 1024px) {
  .cycle-editor-grid {
    grid-template-columns: minmax(0, 1fr) 420px;
  }
}

.cycle-editor-panel,
.cycle-side-section {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 2%);
}

.cycle-editor-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.cycle-panel-header,
.cycle-side-header {
  flex: 0 0 auto;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  padding: 12px 16px;
}

.cycle-panel-header {
  justify-content: space-between;
}

.cycle-phase-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}

.cycle-monitor-panel {
  display: grid;
  grid-template-rows: auto minmax(220px, 1fr) 220px;
  gap: 16px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.cycle-side-section {
  overflow: hidden;
}

.cycle-side-section:first-child {
  padding: 16px;
}

.cycle-side-fill,
.cycle-side-log {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cycle-side-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}
</style>
