<script setup lang="ts">
import { computed } from "vue";
import { NButton, NInput, NPopconfirm, NSelect } from "naive-ui";
import { IconChevronDown, IconChevronRight, IconPlus, IconTrash } from "@tabler/icons-vue";
import SkillCard from "./SkillCard.vue";
import ConditionBuilder from "./ConditionBuilder.vue";
import type { CyclePhase, PhaseFallbackTransition, PhaseTransitionRule } from "../../types/cycle";

interface SkillCardMeta {
  triggerKey: string;
  readbarMs: number;
  cooldownMs: number;
  shotsPerCycle: number;
}

const props = defineProps<{
  phase: CyclePhase;
  phaseIndex: number;
  skillNames: Record<string, string>;
  skillMeta: Record<string, SkillCardMeta>;
  skillOptions: { id: string; name: string }[];
  pointOptions: { id: string; name: string }[];
  markerOptions: { id: string; name: string; allowed_values?: string[] }[];
  timerOptions: { id: string; name: string }[];
  counterOptions: { id: string; name: string }[];
  phaseOptions: { id: string; name: string }[];
  collapsed: boolean;
}>();

const emit = defineEmits<{
  "update:phase": [phase: CyclePhase];
  remove: [];
  addSlot: [];
  editSlot: [index: number];
  removeSlot: [index: number];
  toggleCollapse: [];
}>();

const completeOptions = [
  { label: "全部释放后进入下一阶段", value: "all_fired" },
  { label: "任一释放后进入下一阶段", value: "any_fired" },
  { label: "都未就绪后进入下一阶段", value: "none_ready" },
  { label: "每次执行后立即进入下一阶段", value: "always" },
];

const phaseSelectOptions = computed(() =>
  props.phaseOptions.map((phase) => ({ label: phase.name, value: phase.id }))
);

const fallbackTypeOptions = [
  { label: "停留当前阶段", value: "stay" },
  { label: "进入下一阶段", value: "next" },
  { label: "跳转到阶段", value: "phase" },
];

function completeLabel(value: string) {
  return completeOptions.find((option) => option.value === value)?.label ?? value;
}

function notifyPhaseChanged() {
  emit("update:phase", props.phase);
}

function transitionRules(): PhaseTransitionRule[] {
  if (!props.phase.transition_rules) {
    props.phase.transition_rules = [];
  }
  return props.phase.transition_rules;
}

function firstTargetPhase(): string {
  const currentName = props.phase.name.trim();
  return props.phaseOptions.find((phase) => phase.id !== currentName)?.id ?? props.phaseOptions[0]?.id ?? "";
}

function addTransitionRule() {
  transitionRules().push({
    label: `规则 ${transitionRules().length + 1}`,
    condition_expr: { type: "const", value: true },
    target_phase: firstTargetPhase(),
  });
  notifyPhaseChanged();
}

function removeTransitionRule(index: number) {
  transitionRules().splice(index, 1);
  notifyPhaseChanged();
}

function updateTransitionRule(index: number, patch: Partial<PhaseTransitionRule>) {
  const rule = transitionRules()[index];
  if (!rule) return;
  Object.assign(rule, patch);
  notifyPhaseChanged();
}

function fallbackTransition(): PhaseFallbackTransition {
  return props.phase.fallback_transition ?? { type: "next" };
}

function fallbackType(): PhaseFallbackTransition["type"] {
  return fallbackTransition().type;
}

function fallbackTargetPhase(): string {
  const fallback = fallbackTransition();
  return fallback.type === "phase" ? fallback.target_phase : firstTargetPhase();
}

function setFallbackType(type: PhaseFallbackTransition["type"]) {
  props.phase.fallback_transition =
    type === "phase" ? { type, target_phase: firstTargetPhase() } : { type };
  notifyPhaseChanged();
}

function setFallbackTarget(targetPhase: string) {
  props.phase.fallback_transition = { type: "phase", target_phase: targetPhase };
  notifyPhaseChanged();
}
</script>

<template>
  <div class="phase-lane overflow-hidden rounded border border-white/10 bg-[#121318]">
    <div class="phase-header grid items-center gap-2 border-b border-white/10 bg-white/[0.04] px-3 py-2">
      <n-button size="small" quaternary class="h-8 w-8" @click="emit('toggleCollapse')">
        <template #icon>
          <IconChevronDown v-if="!collapsed" :size="16" />
          <IconChevronRight v-else :size="16" />
        </template>
      </n-button>
      <span class="whitespace-nowrap text-sm font-bold text-gray-200">P{{ phaseIndex + 1 }}</span>
      <n-input
        :value="phase.name"
        size="small"
        placeholder="阶段名称"
        @update:value="(value: string) => { phase.name = value; notifyPhaseChanged(); }"
      />
      <n-select
        :value="phase.complete_when"
        :options="completeOptions"
        size="small"
        @update:value="(value: string) => { phase.complete_when = value as CyclePhase['complete_when']; notifyPhaseChanged(); }"
      />
      <div class="phase-header-spacer min-w-[20px]" />
      <n-popconfirm @positive-click="emit('remove')">
        <template #trigger>
          <n-button size="small" quaternary type="error" class="h-8 w-8">
            <template #icon><IconTrash :size="16" /></template>
          </n-button>
        </template>
        删除该阶段？
      </n-popconfirm>
    </div>

    <div v-if="!collapsed" class="phase-body px-3 py-3">
      <div
        v-if="phase.skills.length > 0"
        class="phase-skill-row flex min-h-[124px] w-full flex-nowrap items-stretch gap-3 overflow-x-auto pb-1"
      >
        <template v-for="(slot, slotIndex) in phase.skills" :key="slotIndex">
          <div class="phase-skill-item flex flex-shrink-0 items-center gap-2">
            <SkillCard
              :slot="slot"
              :index="slotIndex"
              :skill-name="skillNames[slot.skill_id] || null"
              :meta="skillMeta[slot.skill_id] || null"
              @edit="emit('editSlot', slotIndex)"
              @remove="emit('removeSlot', slotIndex)"
            />
            <span v-if="slotIndex < phase.skills.length - 1" class="text-base leading-none text-gray-500">→</span>
          </div>
        </template>

        <n-button size="small" dashed class="phase-add-card h-[112px] w-28 flex-shrink-0" @click="emit('addSlot')">
          <template #icon><IconPlus :size="16" /></template>
          添加技能
        </n-button>
      </div>

      <div
        v-else
        class="phase-empty flex min-h-[124px] flex-col items-center justify-center gap-3 rounded border border-dashed border-white/10 bg-black/10 px-4 py-6 text-center"
      >
        <div>
          <div class="text-sm font-medium text-gray-300">当前阶段还没有技能</div>
          <div class="mt-1 text-xs text-gray-500">添加技能槽后，双击卡片编辑条件、读条和完成检测</div>
        </div>
        <n-button size="small" type="primary" @click="emit('addSlot')">
          <template #icon><IconPlus :size="16" /></template>
          添加技能
        </n-button>
      </div>

      <div class="phase-transitions mt-3 border-t border-white/10 pt-3">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="text-xs font-semibold text-gray-300">阶段跳转规则</div>
            <div class="mt-0.5 text-xs text-gray-500">阶段完成后按顺序检查，命中后跳转到目标阶段</div>
          </div>
          <n-button size="tiny" secondary :disabled="phaseSelectOptions.length === 0" @click="addTransitionRule">
            <template #icon><IconPlus :size="14" /></template>
            添加规则
          </n-button>
        </div>

        <div v-if="transitionRules().length === 0" class="rounded border border-dashed border-white/10 px-3 py-2 text-xs text-gray-500">
          暂无规则。当前阶段完成后使用 fallback。
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="(rule, ruleIndex) in transitionRules()"
            :key="ruleIndex"
            class="transition-row rounded border border-white/10 bg-black/10 p-2"
          >
            <div class="grid gap-2 md:grid-cols-[minmax(120px,180px)_minmax(160px,220px)_auto]">
              <n-input
                :value="rule.label"
                size="small"
                placeholder="规则名称"
                @update:value="(value: string) => updateTransitionRule(ruleIndex, { label: value })"
              />
              <n-select
                :value="rule.target_phase"
                :options="phaseSelectOptions"
                size="small"
                placeholder="目标阶段"
                @update:value="(value: string) => updateTransitionRule(ruleIndex, { target_phase: value })"
              />
              <n-popconfirm @positive-click="removeTransitionRule(ruleIndex)">
                <template #trigger>
                  <n-button size="small" quaternary type="error" class="h-8 w-8 justify-self-start">
                    <template #icon><IconTrash :size="14" /></template>
                  </n-button>
                </template>
                删除该跳转规则？
              </n-popconfirm>
            </div>
            <div class="mt-2">
              <ConditionBuilder
                :model-value="rule.condition_expr as any"
                :skills="skillOptions"
                :points="pointOptions"
                :markers="markerOptions"
                :timers="timerOptions"
                :counters="counterOptions"
                @update:model-value="(value) => updateTransitionRule(ruleIndex, { condition_expr: value as any })"
              />
            </div>
          </div>
        </div>

        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
          <span>Fallback</span>
          <n-select
            :value="fallbackType()"
            :options="fallbackTypeOptions"
            size="tiny"
            style="width: 150px"
            @update:value="(value: PhaseFallbackTransition['type']) => setFallbackType(value)"
          />
          <n-select
            v-if="fallbackType() === 'phase'"
            :value="fallbackTargetPhase()"
            :options="phaseSelectOptions"
            size="tiny"
            placeholder="目标阶段"
            style="width: 180px"
            @update:value="(value: string) => setFallbackTarget(value)"
          />
        </div>
      </div>
    </div>

    <div v-else class="phase-collapsed px-3 py-2 text-xs text-gray-500">
      {{ phase.skills.length }} 个技能 · {{ completeLabel(phase.complete_when) }}
    </div>
  </div>
</template>

<style scoped>
.phase-lane {
  overflow: hidden;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 6px;
  background: #121318;
}

.phase-header {
  grid-template-columns: auto auto minmax(160px, 220px) minmax(220px, 320px) minmax(20px, 1fr) auto;
}

.phase-skill-row {
  scrollbar-width: thin;
}

.phase-add-card {
  flex: 0 0 112px;
}

@media (max-width: 760px) {
  .phase-header {
    grid-template-columns: auto auto minmax(160px, 1fr) auto;
  }

  .phase-header :deep(.n-select) {
    grid-column: 3 / -1;
  }

  .phase-header-spacer {
    display: none;
  }
}
</style>
