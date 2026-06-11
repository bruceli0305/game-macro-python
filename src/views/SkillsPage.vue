<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, h, watch } from "vue";
import {
  NCard, NButton, NSpace, NDataTable, NTag, NModal,
  NInput, NInputNumber, NSwitch, NForm, NFormItem, NDivider,
  NColorPicker, useMessage,
} from "naive-ui";
import { IconPlus, IconEdit, IconTrash, IconDeviceFloppy, IconDownload, IconPointer } from "@tabler/icons-vue";
import Gw2ImportDialog from "../components/editor/Gw2ImportDialog.vue";
import { useCapture } from "../composables/useCapture";
import {
  useProfile,
  withProfileSkills,
} from "../composables/useProfile";
import { firstProfileError, validateProfileForSave } from "../utils/profile-validation";
import { normalizeSkillDraft, validateSkillDraft } from "../utils/skill-validation";
import type { DataTableColumns } from "naive-ui";
import type { AmmoStagePixel, PixelSpec, Skill } from "../types/skill";

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
const pickingAmmoStageIndex = ref<number | null>(null);
const lastSkillCapture = ref(0);
const { captureAtCursor, store: pickerStore } = useCapture();
const { loadActiveProfile, saveActiveProfile } = useProfile();
const message = useMessage();

function defaultPixel(): PixelSpec {
  return {
    monitor: "primary",
    vx: 0,
    vy: 0,
    color: { r: 255, g: 255, b: 255 },
    tolerance: 20,
    sample: { mode: "single", radius: 0 },
  };
}

function toHex(pixel: PixelSpec): string {
  return `#${pixel.color.r.toString(16).padStart(2, "0")}${pixel.color.g.toString(16).padStart(2, "0")}${pixel.color.b.toString(16).padStart(2, "0")}`;
}

function applyHex(pixel: PixelSpec, value: string) {
  if (!/^#[0-9a-fA-F]{6}$/.test(value)) return;
  pixel.color.r = parseInt(value.slice(1, 3), 16);
  pixel.color.g = parseInt(value.slice(3, 5), 16);
  pixel.color.b = parseInt(value.slice(5, 7), 16);
}

async function captureSkillPixel() {
  const now = Date.now();
  if (now - lastSkillCapture.value < 400) {
    pickerStore.recordCaptureIgnored("skills.skill", "debounced");
    return;
  }
  lastSkillCapture.value = now;
  pickerStore.recordCaptureRequest("skills.skill");
  try {
    const result = await captureAtCursor();
    if (!result) {
      pickerStore.recordCaptureFailure("skills.skill", "capture_at_cursor returned empty result");
      return;
    }
    form.pixel.monitor = result.monitor;
    form.pixel.vx = result.x;
    form.pixel.vy = result.y;
    form.pixel.color.r = result.r;
    form.pixel.color.g = result.g;
    form.pixel.color.b = result.b;
    pickerStore.recordCaptureSuccess("skills.skill", `${result.monitor} (${result.x},${result.y}) ${result.hex}`);
    message.success("已更新技能像素点");
  } catch (e) {
    pickerStore.recordCaptureFailure("skills.skill", String(e || "capture failed"));
    message.error("取色失败，请确认屏幕捕获权限和鼠标位置");
  }
}

async function captureAmmoStagePixel(index: number) {
  const now = Date.now();
  const context = `skills.ammo:${index}`;
  if (now - lastSkillCapture.value < 400) {
    pickerStore.recordCaptureIgnored(context, "debounced");
    return;
  }
  lastSkillCapture.value = now;
  const stage = form.ammo_stages[index];
  if (!stage) {
    pickerStore.recordCaptureIgnored(context, "ammo stage missing");
    return;
  }
  pickerStore.recordCaptureRequest(context);
  try {
    const result = await captureAtCursor();
    if (!result) {
      pickerStore.recordCaptureFailure(context, "capture_at_cursor returned empty result");
      return;
    }
    stage.pixel.monitor = result.monitor;
    stage.pixel.vx = result.x;
    stage.pixel.vy = result.y;
    stage.pixel.color.r = result.r;
    stage.pixel.color.g = result.g;
    stage.pixel.color.b = result.b;
    pickerStore.recordCaptureSuccess(context, `${result.monitor} (${result.x},${result.y}) ${result.hex}`);
    message.success(`已更新弹药阶段 ${stage.charges_left} 的像素点`);
  } catch (e) {
    pickerStore.recordCaptureFailure(context, String(e || "capture failed"));
    message.error("取色失败，请确认屏幕捕获权限和鼠标位置");
  }
}

function stopAnyPicking() {
  window.removeEventListener("picker:capture", captureSkillPixel);
  for (let index = 0; index < form.ammo_stages.length; index += 1) {
    window.removeEventListener("picker:capture", ammoCaptureHandlers[index]);
  }
  pickingSkillPixel.value = false;
  pickingAmmoStageIndex.value = null;
}

const ammoCaptureHandlers: Array<() => void> = [];

function ammoHandler(index: number): () => void {
  if (!ammoCaptureHandlers[index]) {
    ammoCaptureHandlers[index] = () => captureAmmoStagePixel(index);
  }
  return ammoCaptureHandlers[index];
}

// 弹窗打开/关闭时管理 F8 监听
watch(showModal, (val) => {
  if (val) {
    pickingSkillPixel.value = false;
    pickingAmmoStageIndex.value = null;
  } else {
    stopAnyPicking();
  }
});

function toggleSkillPicking() {
  if (pickingSkillPixel.value) {
    stopAnyPicking();
  } else {
    stopAnyPicking();
    window.addEventListener("picker:capture", captureSkillPixel);
    pickingSkillPixel.value = true;
  }
}

function toggleAmmoPicking(index: number) {
  if (pickingAmmoStageIndex.value === index) {
    stopAnyPicking();
    return;
  }

  stopAnyPicking();
  window.addEventListener("picker:capture", ammoHandler(index));
  pickingAmmoStageIndex.value = index;
}

function addAmmoStage() {
  const nextCharges = form.ammo_stages.length === 0
    ? 1
    : Math.max(...form.ammo_stages.map((stage) => stage.charges_left)) + 1;
  const stage: AmmoStagePixel = {
    charges_left: nextCharges,
    pixel: defaultPixel(),
  };
  form.ammo_stages.push(stage);
}

function removeAmmoStage(index: number) {
  if (pickingAmmoStageIndex.value === index) stopAnyPicking();
  form.ammo_stages.splice(index, 1);
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
  { title: "弹药阶段", key: "ammo_stages", width: 90, render: (row: Skill) => String(row.ammo_stages.length) },
  {
    title: "显示器", key: "pixel.monitor", width: 130,
    ellipsis: { tooltip: true },
    render: (row: Skill) => row.pixel.monitor || "primary",
  },
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
  const draft = normalizeSkillDraft(JSON.parse(JSON.stringify(form)) as Skill);
  const error = validateSkillDraft(draft, {
    existingSkills: skills.value,
    editingIndex: editingIndex.value,
  });
  if (error) {
    message.error(error);
    return;
  }

  if (editingIndex.value >= 0) {
    skills.value[editingIndex.value] = draft;
  } else {
    skills.value.push(draft);
  }
  showModal.value = false;
}

function removeSkill(index: number) {
  skills.value.splice(index, 1);
}

// ---- 持久化 ----
async function loadSkills() {
  try {
    const profile = await loadActiveProfile();
    skills.value = profile.skills.skills;
  } catch (e) {
    skills.value = [];
    message.error(String(e || "加载技能配置失败"));
  }
}

async function persistSkills() {
  try {
    const profile = await loadActiveProfile();
    const next = withProfileSkills(profile, JSON.parse(JSON.stringify(skills.value)) as Skill[]);
    const error = firstProfileError(validateProfileForSave(next));
    if (error) {
      message.error(error);
      return;
    }
    await saveActiveProfile(next);
    message.success("技能配置已保存");
  } catch (e) {
    message.error("保存技能失败");
  }
}

function onActiveProfileChanged() {
  void loadSkills();
}

onMounted(() => {
  window.addEventListener("profile:active-changed", onActiveProfileChanged);
  void loadSkills();
});
onUnmounted(() => window.removeEventListener("profile:active-changed", onActiveProfileChanged));
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
        style="width:720px; max-height:80vh; overflow-y:auto"
        closable
        @close="showModal = false"
      >
        <n-form label-placement="left" label-width="80" size="small">
          <n-form-item label="ID">
            <n-input v-model:value="form.id" placeholder="唯一技能 ID" />
          </n-form-item>
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
          <n-form-item label="每轮次数">
            <n-input-number v-model:value="form.shots_per_cycle" :min="0" :max="99" />
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
          <div
            v-if="pickingSkillPixel || pickingAmmoStageIndex !== null || pickerStore.captureRequestCount > 0 || pickerStore.captureIgnoredCount > 0"
            class="mb-3 grid grid-cols-1 gap-2 rounded border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-gray-300 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
          >
            <div>
              取色处理：请求 {{ pickerStore.captureRequestCount }} · 成功 {{ pickerStore.captureSuccessCount }} · 失败 {{ pickerStore.captureFailureCount }} · 忽略 {{ pickerStore.captureIgnoredCount }}
            </div>
            <div class="truncate text-gray-400" :title="pickerStore.lastCaptureMessage">
              最近：{{ pickerStore.lastCaptureStatus }} · {{ pickerStore.lastCaptureContext || '无' }} · {{ pickerStore.lastCaptureMessage || '无' }}
            </div>
          </div>
          <n-form-item label="位置">
            <n-space>
              <n-input-number v-model:value="form.pixel.vx" size="small" style="width:100px" placeholder="X" />
              <n-input-number v-model:value="form.pixel.vy" size="small" style="width:100px" placeholder="Y" />
            </n-space>
          </n-form-item>
          <n-form-item label="显示器">
            <n-input v-model:value="form.pixel.monitor" placeholder="primary" />
          </n-form-item>
          <n-form-item label="容差">
            <n-input-number v-model:value="form.pixel.tolerance" :min="0" :max="255" />
          </n-form-item>
          <n-form-item label="目标颜色">
            <n-color-picker
              :value="toHex(form.pixel)"
              @update:value="(v: string) => applyHex(form.pixel, v)"
            />
          </n-form-item>

          <n-divider>弹药阶段</n-divider>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-xs text-gray-400">按剩余弹药层数配置像素，任一阶段匹配即视为有可用弹药。</span>
              <n-button size="tiny" dashed @click="addAmmoStage">
                <template #icon><IconPlus /></template>
                添加阶段
              </n-button>
            </div>

            <div
              v-for="(stage, index) in form.ammo_stages"
              :key="index"
              class="rounded border border-white/10 bg-white/[0.03] p-3"
            >
              <div class="mb-3 flex items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">剩余层数</span>
                  <n-input-number
                    v-model:value="stage.charges_left"
                    size="tiny"
                    :min="0"
                    :max="99"
                    style="width: 92px"
                  />
                </div>
                <n-space size="small">
                  <n-button
                    size="tiny"
                    :type="pickingAmmoStageIndex === index ? 'error' : 'primary'"
                    @click="toggleAmmoPicking(index)"
                  >
                    <template #icon><IconPointer /></template>
                    {{ pickingAmmoStageIndex === index ? '停止取色' : '取色' }}
                  </n-button>
                  <n-button size="tiny" quaternary type="error" @click="removeAmmoStage(index)">
                    <template #icon><IconTrash /></template>
                  </n-button>
                </n-space>
              </div>

              <div class="grid grid-cols-[1fr_1fr_1fr] gap-3">
                <n-form-item label="X" label-placement="top" :show-feedback="false">
                  <n-input-number v-model:value="stage.pixel.vx" size="tiny" />
                </n-form-item>
                <n-form-item label="Y" label-placement="top" :show-feedback="false">
                  <n-input-number v-model:value="stage.pixel.vy" size="tiny" />
                </n-form-item>
                <n-form-item label="容差" label-placement="top" :show-feedback="false">
                  <n-input-number v-model:value="stage.pixel.tolerance" size="tiny" :min="0" :max="255" />
                </n-form-item>
              </div>

              <n-form-item label="显示器" label-placement="top" :show-feedback="false" class="mt-2">
                <n-input v-model:value="stage.pixel.monitor" size="small" placeholder="primary" />
              </n-form-item>

              <n-form-item label="目标颜色" label-placement="top" :show-feedback="false" class="mt-2">
                <n-color-picker
                  :value="toHex(stage.pixel)"
                  size="small"
                  @update:value="(v: string) => applyHex(stage.pixel, v)"
                />
              </n-form-item>
            </div>

            <div
              v-if="form.ammo_stages.length === 0"
              class="rounded border border-dashed border-white/10 bg-black/10 px-3 py-4 text-center text-xs text-gray-500"
            >
              未配置弹药阶段时，引擎只按技能冷却和技能像素判断可释放状态。
            </div>
          </div>
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
