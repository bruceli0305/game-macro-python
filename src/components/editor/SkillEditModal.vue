<script setup lang="ts">
import { reactive, watch, ref, onMounted } from "vue";
import { NModal, NCard, NButton, NSpace, NInput, NInputNumber, NSelect } from "naive-ui";
import ConditionBuilder from "./ConditionBuilder.vue";
import type { SkillSlot } from "../../types/cycle";

const props = defineProps<{
  show: boolean;
  slot: SkillSlot;
  skillOptions: { id: string; name: string }[];
  pointOptions: { id: string; name: string }[];
}>();

const emit = defineEmits<{
  "update:show": [v: boolean];
  saved: [slot: SkillSlot];
}>();

const form = reactive<SkillSlot>({
  skill_id: "",
  priority: 1,
  label: "",
  condition_expr: null,
  start_expr: null,
  complete_expr: null,
  override_cast_ms: null,
});

watch(() => props.show, (val) => {
  if (val) Object.assign(form, JSON.parse(JSON.stringify(props.slot)));
});

// 从技能列表加载名称
const skillList = ref<{ id: string; name: string }[]>([]);
onMounted(() => {
  skillList.value = props.skillOptions;
});

function save() {
  emit("saved", JSON.parse(JSON.stringify(form)));
  emit("update:show", false);
}
</script>

<template>
  <n-modal :show="props.show" @update:show="(v: boolean) => emit('update:show', v)">
    <n-card title="编辑技能" style="width:500px; max-height:80vh; overflow-y:auto" closable @close="emit('update:show', false)">
      <n-space vertical size="small">
        <n-select
          v-model:value="form.skill_id"
          :options="skillList.map(s => ({ label: s.name || s.id, value: s.id }))"
          size="small"
          filterable
          placeholder="选择技能"
        />
        <n-input v-model:value="form.label" size="small" placeholder="显示标签（可选）" />
        <n-input-number v-model:value="form.priority" size="small" :min="1" :max="99" placeholder="优先级" />
        <n-input-number v-model:value="form.override_cast_ms" size="small" :min="0" placeholder="覆盖读条时间(ms)" />

        <div class="text-xs text-gray-400 pt-2">条件表达式</div>
        <ConditionBuilder
          :model-value="form.condition_expr as any"
          :skills="skillList"
          :points="pointOptions"
          @update:model-value="(v: any) => (form.condition_expr as any) = v"
        />
        <div class="text-xs text-gray-400 pt-2">Start Expr</div>
        <ConditionBuilder
          :model-value="form.start_expr as any"
          :skills="skillList"
          :points="pointOptions"
          @update:model-value="(v: any) => (form.start_expr as any) = v"
        />
        <div class="text-xs text-gray-400 pt-2">Complete Expr</div>
        <ConditionBuilder
          :model-value="form.complete_expr as any"
          :skills="skillList"
          :points="pointOptions"
          @update:model-value="(v: any) => (form.complete_expr as any) = v"
        />
      </n-space>

      <n-space justify="end" class="mt-4">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" @click="save">确定</n-button>
      </n-space>
    </n-card>
  </n-modal>
</template>
