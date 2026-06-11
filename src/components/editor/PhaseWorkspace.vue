<script setup lang="ts">
import { computed } from "vue";
import { NButton, NSelect } from "naive-ui";
import { IconPlus } from "@tabler/icons-vue";
import PhaseLane from "./PhaseLane.vue";
import type {
  CycleConfig,
  PhaseFallbackTransition,
  RuntimeAction,
  SkillSlot,
  SkillSlotRole,
} from "../../types/cycle";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

type Option = { id: string; name: string };
type RoleCounts = Record<SkillSlotRole, number>;
type PhaseConfig = CycleConfig["phases"][number];

const props = defineProps<{
  config: CycleConfig;
  selectedPhaseIndex: number;
  engineRunning: boolean;
  currentPhase: number;
  skillNames: Record<string, string>;
  skillMeta: Record<string, SkillCardMeta>;
  skillOptions: Option[];
  pointOptions: Option[];
  markerOptions: Option[];
  timerOptions: Option[];
  counterOptions: Option[];
  phaseOptions: Option[];
  completeWhenOptions: { label: string; value: string }[];
  roleLabels: Record<SkillSlotRole, string>;
  phaseDisplayName: (phase: PhaseConfig, index: number) => string;
  completeLabel: (value: string) => string;
  phaseRoleCounts: (phase: PhaseConfig) => RoleCounts;
  skillDisplayName: (skillId: string) => string;
  exprSummary: (value: Record<string, unknown> | null | undefined) => string;
  runtimeActionSummary: (action: RuntimeAction) => string;
  fallbackSummary: (fallback: PhaseFallbackTransition | null | undefined) => string;
  slotTriggerKey: (slot: SkillSlot) => string;
  slotAttemptSummary: (slot: SkillSlot) => string;
}>();

const emit = defineEmits<{
  addPhase: [];
  selectPhase: [index: number];
  setCompleteWhen: [value: string];
  updatePhase: [phase: PhaseConfig];
  removePhase: [];
  addSlot: [role: SkillSlotRole];
  editSlot: [slotIndex: number];
  removeSlot: [slotIndex: number];
  toggleCollapse: [];
}>();

const selectedPhase = computed(() => props.config.phases[props.selectedPhaseIndex] ?? null);
const roleOrder: SkillSlotRole[] = ["mandatory", "priority", "filler"];

function roleSlots(role: SkillSlotRole): SkillSlot[] {
  return [
    ...(selectedPhase.value?.skills.filter((slot) => (slot.slot_role ?? "mandatory") === role) ??
      []),
  ].sort((a, b) => a.priority - b.priority);
}

function emitCompleteWhen(value: string | number) {
  emit("setCompleteWhen", String(value));
}

function emitUpdatePhase(phase: PhaseConfig) {
  emit("updatePhase", phase);
}

function emitRemovePhase() {
  emit("removePhase");
}

function emitAddSlot(role: SkillSlotRole = "mandatory") {
  emit("addSlot", role);
}

function emitEditSlot(slotIndex: number) {
  emit("editSlot", slotIndex);
}

function emitRemoveSlot(slotIndex: number) {
  emit("removeSlot", slotIndex);
}

function emitToggleCollapse() {
  emit("toggleCollapse");
}
</script>

<template>
  <div class="cycle-workbench">
    <aside class="phase-navigator" aria-label="阶段导航">
      <div class="phase-navigator-header">
        <div>
          <h2>阶段导航</h2>
          <p>选择一个阶段后在右侧编辑</p>
        </div>
        <n-button size="tiny" secondary @click="emit('addPhase')">
          <template #icon><IconPlus :size="14" /></template>
          新阶段
        </n-button>
      </div>

      <div class="phase-nav-list">
        <button
          v-for="(phase, pi) in config.phases"
          :key="pi"
          class="phase-nav-item"
          :class="{
            active: selectedPhaseIndex === pi,
            running: engineRunning && currentPhase === pi,
          }"
          type="button"
          @click="emit('selectPhase', pi)"
        >
          <span class="phase-nav-index">P{{ pi + 1 }}</span>
          <span class="phase-nav-main">
            <strong>{{ phaseDisplayName(phase, pi) }}</strong>
            <em>{{ completeLabel(phase.complete_when) }}</em>
          </span>
          <span class="phase-nav-counts">
            <span>必 {{ phaseRoleCounts(phase).mandatory }}</span>
            <span>优 {{ phaseRoleCounts(phase).priority }}</span>
            <span>填 {{ phaseRoleCounts(phase).filler }}</span>
          </span>
        </button>
      </div>
    </aside>

    <section class="phase-focus">
      <div class="phase-focus-header">
        <div>
          <h2>阶段编辑</h2>
          <p v-if="selectedPhase">
            P{{ selectedPhaseIndex + 1 }} · {{ phaseDisplayName(selectedPhase, selectedPhaseIndex) }}
          </p>
          <p v-else>当前没有阶段</p>
        </div>
        <div class="phase-focus-actions">
          <n-button
            size="small"
            :disabled="selectedPhaseIndex <= 0"
            @click="emit('selectPhase', selectedPhaseIndex - 1)"
          >
            上一阶段
          </n-button>
          <n-button
            size="small"
            :disabled="selectedPhaseIndex >= config.phases.length - 1"
            @click="emit('selectPhase', selectedPhaseIndex + 1)"
          >
            下一阶段
          </n-button>
        </div>
      </div>

      <div class="phase-focus-body">
        <section v-if="selectedPhase" class="phase-rule-summary">
          <div class="summary-section">
            <div class="summary-section-title">阶段完成</div>
            <div class="summary-grid">
              <div class="summary-item">
                <span>完成方式</span>
                <n-select
                  :value="selectedPhase.complete_when"
                  :options="completeWhenOptions"
                  size="small"
                  style="width: 160px"
                  @update:value="emitCompleteWhen"
                />
              </div>
              <div class="summary-item">
                <span>参与完成</span>
                <strong>
                  必放 {{ phaseRoleCounts(selectedPhase).mandatory }}
                  <template v-if="phaseRoleCounts(selectedPhase).mandatory === 0">
                    · 无必放时由非填充决定
                  </template>
                </strong>
              </div>
              <div class="summary-item">
                <span>入口动作</span>
                <strong>
                  <template v-if="(selectedPhase.entry_actions ?? []).length > 0">
                    {{ (selectedPhase.entry_actions ?? []).map(runtimeActionSummary).join("；") }}
                  </template>
                  <template v-else>无</template>
                </strong>
              </div>
              <div class="summary-item">
                <span>Fallback</span>
                <strong>{{ fallbackSummary(selectedPhase.fallback_transition) }}</strong>
              </div>
            </div>
          </div>

          <div class="summary-section">
            <div class="summary-section-title">帧级候选与优先级</div>
            <p class="summary-section-note">
              每个 tick 先读取当前帧状态，再按顺位从小到大检查候选技能；只有形态、冷却、次数和触发条件都满足时才会发送按键。
            </p>
            <div class="summary-role-list">
              <div v-for="role in roleOrder" :key="role" class="summary-role">
                <div class="summary-role-title">
                  <span>{{ roleLabels[role] }}</span>
                  <em>{{ roleSlots(role).length }}</em>
                </div>
                <div v-if="roleSlots(role).length === 0" class="summary-empty">
                  无{{ roleLabels[role] }}技能
                </div>
                <div v-else class="summary-skill-list">
                  <article
                    v-for="slot in roleSlots(role)"
                    :key="`${role}-${slot.priority}-${slot.skill_id}`"
                    class="summary-skill"
                  >
                    <header>
                      <strong>{{ skillDisplayName(slot.skill_id) }}</strong>
                      <span>按键 {{ slotTriggerKey(slot) }} · 顺位 {{ slot.priority }}</span>
                    </header>
                    <dl>
                      <div>
                        <dt>硬条件</dt>
                        <dd>{{ exprSummary(slot.condition_expr) }}</dd>
                      </div>
                      <div>
                        <dt>就绪信号</dt>
                        <dd>
                          {{ exprSummary(slot.readiness_expr) }}
                          · {{ slot.readiness_policy === "advisory" ? "仅记录" : "必须满足" }}
                        </dd>
                      </div>
                      <div>
                        <dt>施法确认</dt>
                        <dd>{{ exprSummary(slot.start_expr) }}</dd>
                      </div>
                      <div>
                        <dt>完成确认</dt>
                        <dd>{{ exprSummary(slot.complete_expr) }}</dd>
                      </div>
                      <div>
                        <dt>确认策略</dt>
                        <dd>{{ slotAttemptSummary(slot) }}</dd>
                      </div>
                    </dl>
                  </article>
                </div>
              </div>
            </div>
          </div>

          <div class="summary-section">
            <div class="summary-section-title">跳转出口</div>
            <div v-if="(selectedPhase.transition_rules ?? []).length === 0" class="summary-empty">
              无显式跳转规则，阶段完成后使用 Fallback。
            </div>
            <div v-else class="summary-transition-list">
              <article
                v-for="(rule, ruleIndex) in selectedPhase.transition_rules"
                :key="`${ruleIndex}-${rule.label}`"
                class="summary-transition"
              >
                <strong>{{ rule.label || `规则 ${ruleIndex + 1}` }}</strong>
                <span>
                  如果 {{ exprSummary(rule.condition_expr) }}，跳转到
                  {{ rule.target_phase || "未设置目标阶段" }}
                </span>
              </article>
            </div>
          </div>
        </section>

        <PhaseLane
          v-if="selectedPhase"
          :key="selectedPhaseIndex"
          :phase="selectedPhase"
          :phase-index="selectedPhaseIndex"
          :skill-names="skillNames"
          :skill-meta="skillMeta"
          :skill-options="skillOptions"
          :point-options="pointOptions"
          :marker-options="markerOptions"
          :timer-options="timerOptions"
          :counter-options="counterOptions"
          :phase-options="phaseOptions"
          :collapsed="false"
          :style="
            engineRunning && currentPhase === selectedPhaseIndex
              ? 'border-color: #18a058; box-shadow: 0 0 8px rgba(24,160,88,0.3)'
              : ''
          "
          @update:phase="emitUpdatePhase"
          @remove="emitRemovePhase"
          @add-slot="emitAddSlot"
          @edit-slot="emitEditSlot"
          @remove-slot="emitRemoveSlot"
          @toggle-collapse="emitToggleCollapse"
        />

        <div v-else class="phase-empty-state">
          <h3>还没有阶段</h3>
          <p>创建阶段后再配置技能槽、跳转规则和完成条件。</p>
          <n-button size="small" type="primary" @click="emit('addPhase')">
            <template #icon><IconPlus /></template>
            添加阶段
          </n-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.cycle-workbench {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  flex: 1 1 auto;
  min-height: 0;
  gap: 12px;
}

.phase-navigator,
.phase-focus {
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(255 255 255 / 2%);
}

.phase-navigator,
.phase-focus {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.phase-navigator-header,
.phase-focus-header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
  padding: 12px 16px;
}

.phase-navigator-header h2,
.phase-focus-header h2 {
  color: #f3f4f6;
  font-size: 14px;
  font-weight: 700;
}

.phase-navigator-header p,
.phase-focus-header p {
  margin-top: 2px;
  color: #6b7280;
  font-size: 12px;
}

.phase-nav-list,
.phase-focus-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 10px;
}

.phase-rule-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
  border: 1px solid rgb(94 234 212 / 18%);
  border-radius: 6px;
  background: rgb(94 234 212 / 4%);
  padding: 12px;
}

.summary-section {
  min-width: 0;
}

.summary-section + .summary-section {
  border-top: 1px solid rgb(255 255 255 / 8%);
  padding-top: 10px;
}

.summary-section-title {
  margin-bottom: 8px;
  color: #ccfbf1;
  font-size: 12px;
  font-weight: 800;
}

.summary-section-note {
  margin: -2px 0 8px;
  color: #93a4b7;
  font-size: 12px;
  line-height: 1.5;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.summary-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 5px;
  background: rgb(0 0 0 / 12%);
  padding: 8px;
}

.summary-item span,
.summary-skill dt {
  color: #8b949e;
  font-size: 11px;
}

.summary-item strong {
  overflow-wrap: anywhere;
  color: #e5e7eb;
  font-size: 12px;
  font-weight: 600;
}

.summary-role-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-role {
  min-width: 0;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 5px;
  background: rgb(0 0 0 / 12%);
  padding: 8px;
}

.summary-role-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.summary-role-title span {
  color: #f3f4f6;
  font-size: 12px;
  font-weight: 800;
}

.summary-role-title em {
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
  color: #9ca3af;
  font-size: 11px;
  font-style: normal;
  padding: 1px 7px;
}

.summary-empty {
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 5px;
  color: #6b7280;
  font-size: 12px;
  padding: 8px;
  text-align: center;
}

.summary-skill-list,
.summary-transition-list {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
}

.summary-skill,
.summary-transition {
  min-width: 0;
  border-radius: 5px;
  background: rgb(255 255 255 / 4%);
  padding: 8px;
}

.summary-skill header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.summary-skill header strong,
.summary-transition strong {
  overflow: hidden;
  color: #f9fafb;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-skill header span {
  flex: 0 0 auto;
  color: #9ca3af;
  font-size: 11px;
}

.summary-skill dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
  margin: 0;
}

.summary-skill dl div {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 6px;
}

.summary-skill dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: #d1d5db;
  font-size: 11px;
}

.summary-transition {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-transition span {
  overflow-wrap: anywhere;
  color: #d1d5db;
  font-size: 12px;
}

.phase-nav-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.phase-nav-item {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 6px;
  background: rgb(0 0 0 / 12%);
  color: #d1d5db;
  padding: 9px;
  text-align: left;
  cursor: pointer;
}

.phase-nav-item:hover,
.phase-nav-item.active {
  border-color: rgb(94 234 212 / 36%);
  background: rgb(94 234 212 / 9%);
}

.phase-nav-item.running {
  border-color: rgb(24 160 88 / 70%);
  box-shadow: inset 3px 0 0 #18a058;
}

.phase-nav-index {
  display: inline-flex;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: rgb(255 255 255 / 8%);
  color: #f9fafb;
  font-size: 12px;
  font-weight: 800;
}

.phase-nav-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.phase-nav-main strong {
  overflow: hidden;
  color: #e5e7eb;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-nav-main em {
  color: #8b949e;
  font-size: 11px;
  font-style: normal;
}

.phase-nav-counts {
  grid-column: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.phase-nav-counts span {
  border-radius: 4px;
  background: rgb(255 255 255 / 6%);
  color: #9ca3af;
  font-size: 10px;
  padding: 2px 5px;
}

.phase-focus-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.phase-empty-state {
  display: flex;
  min-height: 280px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: rgb(0 0 0 / 10%);
  color: #9ca3af;
  text-align: center;
}

.phase-empty-state h3 {
  color: #e5e7eb;
  font-size: 15px;
  font-weight: 700;
}

@media (max-width: 980px) {
  .cycle-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .phase-navigator {
    max-height: 280px;
  }

  .summary-role-list {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .phase-focus-header {
    align-items: stretch;
    flex-direction: column;
  }

  .summary-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
