<script setup lang="ts">
import { ref, reactive, onMounted, h, watch } from "vue";
import {
  NCard, NButton, NSpace, NDataTable, NTag, NModal,
  NInput, NInputNumber, NSwitch, NForm, NFormItem, NDivider,
  NColorPicker,
} from "naive-ui";
import { IconPlus, IconEdit, IconTrash, IconDeviceFloppy, IconDownload, IconPointer } from "@tabler/icons-vue";
import Gw2ImportDialog from "../components/editor/Gw2ImportDialog.vue";
import { useCapture } from "../composables/useCapture";
import { DEFAULT_PROFILE_NAME, useProfile } from "../composables/useProfile";
import type { DataTableColumns } from "naive-ui";
import type { Skill } from "../types/skill";

// ---- 状态 ----
const skills = ref<Skill[]>([]);
const showModal = ref(false);
const showImport = ref(false);
const editingIndex = ref(-1);

const defaultSkill = (): Skill => ({
  id: String(Date.now()),
  name: "新技能",
  enabled: true,
  trigger_key: "",
  cast: { readbar_ms: 0, cooldown_ms: 0 },
  pixel: {
    monitor: "primary", vx: 0, vy: 0,
    color: { r: 255, g: 255, b: 255 },
    tolerance: 20,
    sample: { mode: "single", radius: 0 },
  },
  note: "",
  game_id: 0, game_desc: "", icon_url: "", cooldown_ms: 0, radius: 0,
  shots_per_cycle: 1, ammo_stages: [],
});

const form = reactive<Skill>(defaultSkill());
const pickingSkillPixel = ref(false);
const lastSkillCapture = ref(0);
const { captureAtCursor } = useCapture();
const { loadOrCreateProfile, saveSkills } = useProfile();

async function captureSkillPixel() {
  const now = Date.now();
  if (now - lastSkillCapture.value < 400) return;
  lastSkillCapture.value = now;
  try {
    const result = await captureAtCursor();
    if (!result) return;
    form.pixel.vx = result.x;
    form.pixel.vy = result.y;
    form.pixel.color.r = result.r;
    form.pixel.color.g = result.g;
    form.pixel.color.b = result.b;
  } catch (e) { console.error("取色失败:", e); }
}

// 弹窗打开/关闭时管理 F8 监听
watch(showModal, (val) => {
  if (val) {
    pickingSkillPixel.value = false;
  } else {
    // 关闭时清理
    if (pickingSkillPixel.value) {
      window.removeEventListener("picker:capture", captureSkillPixel);
      pickingSkillPixel.value = false;
    }
  }
});

function toggleSkillPicking() {
  if (pickingSkillPixel.value) {
    window.removeEventListener("picker:capture", captureSkillPixel);
    pickingSkillPixel.value = false;
  } else {
    // 先移除可能存在的其他监听器（PointsPage 的）
    window.removeEventListener("picker:capture", captureSkillPixel);
    window.addEventListener("picker:capture", captureSkillPixel);
    pickingSkillPixel.value = true;
  }
}

// ---- 表格列 ----
const columns: DataTableColumns<Skill> = [
  { title: "名称", key: "name", width: 120 },
  { title: "按键", key: "trigger_key", width: 80 },
  {
    title: "启用", key: "enabled", width: 60,
    render: (row: Skill) => {
      return row.enabled
        ? h(NTag, { type: "success", size: "small" }, { default: () => "启用" })
        : h(NTag, { type: "default", size: "small" }, { default: () => "禁用" });
    },
  },
  { title: "读条(ms)", key: "cast.readbar_ms", width: 80, render: (row: Skill) => String(row.cast.readbar_ms) },
  { title: "冷却(ms)", key: "cooldown_ms", width: 80, render: (row: Skill) => String(row.cooldown_ms) },
  {
    title: "操作", key: "actions", width: 100,
    render: (_row: Skill, index: number) =>
      h(NSpace, { size: "small" }, {
        default: () => [
          h(NButton, { size: "tiny", quaternary: true, onClick: () => editSkill(index) }, { icon: () => h(IconEdit) }),
          h(NButton, { size: "tiny", quaternary: true, type: "error", onClick: () => removeSkill(index) }, { icon: () => h(IconTrash) }),
        ],
      }),
  },
];

// ---- CRUD ----
function openCreate() {
  editingIndex.value = -1;
  Object.assign(form, defaultSkill());
  showModal.value = true;
}

function editSkill(index: number) {
  editingIndex.value = index;
  Object.assign(form, JSON.parse(JSON.stringify(skills.value[index])));
  showModal.value = true;
}

function saveSkill() {
  if (editingIndex.value >= 0) {
    skills.value[editingIndex.value] = JSON.parse(JSON.stringify(form));
  } else {
    skills.value.push(JSON.parse(JSON.stringify(form)));
  }
  showModal.value = false;
}

function removeSkill(index: number) {
  skills.value.splice(index, 1);
}

// ---- 持久化 ----
async function loadSkills() {
  try {
    const profile = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    skills.value = profile.skills.skills;
  } catch {
    console.log("未找到已保存的 profile，使用空列表");
  }
}

async function persistSkills() {
  try {
    await saveSkills(DEFAULT_PROFILE_NAME, skills.value);
    // 加载现有 profile，更新 skills 部分
  } catch (e) {
    console.error("保存失败:", e);
  }
}

onMounted(() => loadSkills());
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">技能管理</h1>
      <n-space>
        <n-button size="small" @click="persistSkills">
          <template #icon><IconDeviceFloppy /></template>
          保存
        </n-button>
        <n-button size="small" @click="showImport = true">
          <template #icon><IconDownload /></template>
          导入 GW2
        </n-button>
        <n-button size="small" type="primary" @click="openCreate">
          <template #icon><IconPlus /></template>
          新建技能
        </n-button>
      </n-space>
    </div>

    <n-card>
      <n-data-table
        :columns="columns"
        :data="skills"
        :bordered="false"
        size="small"
        :max-height="500"
        virtual-scroll
      />
    </n-card>

    <!-- 编辑弹窗 -->
    <n-modal :show="showModal" @update:show="showModal = $event">
      <n-card
        :title="editingIndex >= 0 ? '编辑技能' : '新建技能'"
        style="width:500px; max-height:80vh; overflow-y:auto"
        closable
        @close="showModal = false"
      >
        <n-form label-placement="left" label-width="80" size="small">
          <n-form-item label="名称">
            <n-input v-model:value="form.name" />
          </n-form-item>
          <n-form-item label="触发键">
            <n-input v-model:value="form.trigger_key" placeholder="如 1, 2, f1" />
          </n-form-item>
          <n-form-item label="启用">
            <n-switch v-model:value="form.enabled" />
          </n-form-item>

          <n-divider>施法参数</n-divider>
          <n-form-item label="读条(ms)">
            <n-input-number v-model:value="form.cast.readbar_ms" :min="0" :max="600000" />
          </n-form-item>
          <n-form-item label="冷却(ms)">
            <n-input-number v-model:value="form.cooldown_ms" :min="0" :max="600000" />
          </n-form-item>

          <n-divider>像素检测</n-divider>
          <n-form-item label="">
            <n-button
              size="small"
              :type="pickingSkillPixel ? 'error' : 'primary'"
              @click="toggleSkillPicking"
            >
              <template #icon><IconPointer /></template>
              {{ pickingSkillPixel ? '停止取色 (F8)' : '开始取色' }}
            </n-button>
            <span v-if="pickingSkillPixel" class="text-xs text-green-400 ml-2">移动鼠标到目标位置，按 F8</span>
          </n-form-item>
          <n-form-item label="位置">
            <n-space>
              <n-input-number v-model:value="form.pixel.vx" size="small" style="width:100px" placeholder="X" />
              <n-input-number v-model:value="form.pixel.vy" size="small" style="width:100px" placeholder="Y" />
            </n-space>
          </n-form-item>
          <n-form-item label="容差">
            <n-input-number v-model:value="form.pixel.tolerance" :min="0" :max="255" />
          </n-form-item>
          <n-form-item label="目标颜色">
            <n-color-picker
              :value="`#${form.pixel.color.r.toString(16).padStart(2,'0')}${form.pixel.color.g.toString(16).padStart(2,'0')}${form.pixel.color.b.toString(16).padStart(2,'0')}`"
              @update:value="(v: string) => {
                form.pixel.color.r = parseInt(v.slice(1,3), 16);
                form.pixel.color.g = parseInt(v.slice(3,5), 16);
                form.pixel.color.b = parseInt(v.slice(5,7), 16);
              }"
            />
          </n-form-item>
        </n-form>

        <n-space justify="end" class="mt-4">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" @click="saveSkill">确定</n-button>
        </n-space>
      </n-card>
    </n-modal>

    <Gw2ImportDialog
      :show="showImport"
      @update:show="showImport = $event"
      @imported="(gw2Skills: any[]) => {
        for (const gs of gw2Skills) {
          skills.push({
            id: `gw2_${gs.id}`,
            name: gs.name,
            enabled: true,
            trigger_key: '',
            cast: { readbar_ms: 0, cooldown_ms: 0 },
            pixel: { monitor: 'primary', vx: 0, vy: 0, color: { r: 255, g: 255, b: 255 }, tolerance: 20, sample: { mode: 'single', radius: 0 } },
            note: gs.description || '',
            game_id: gs.id,
            game_desc: gs.description || '',
            icon_url: '',
            cooldown_ms: gs.cooldown_ms,
            radius: gs.radius,
            shots_per_cycle: 1,
            ammo_stages: [],
          });
        }
      }"
    />
  </div>
</template>
