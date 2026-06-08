<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NSpace,
  NSwitch,
  NText,
  useMessage,
} from "naive-ui";
import { IconDeviceFloppy } from "@tabler/icons-vue";
import { DEFAULT_PROFILE_NAME, cloneProfile, useProfile } from "../composables/useProfile";
import type { BaseConfig, Profile } from "../types/profile";

const message = useMessage();
const { loadOrCreateProfile, saveProfile } = useProfile();
const loading = ref(false);
const saving = ref(false);
const profile = ref<Profile | null>(null);

const base = reactive<BaseConfig>({
  schema_version: 2,
  ui: { theme: "darkly" },
  capture: { monitor_policy: "primary" },
  pick: {
    confirm_hotkey: "f8",
    mouse_avoid: true,
    mouse_avoid_offset_y: 80,
    mouse_avoid_settle_ms: 80,
  },
  io: { auto_save: true, backup_on_save: false },
  cast_bar: {
    mode: "timer",
    point_id: "",
    tolerance: 15,
    poll_interval_ms: 30,
    max_wait_factor: 1.5,
  },
  exec: {
    enabled: false,
    toggle_hotkey: "",
    default_skill_gap_ms: 50,
    poll_not_ready_ms: 50,
    max_retries: 3,
    retry_gap_ms: 30,
  },
});

function assignBase(next: BaseConfig) {
  Object.assign(base, cloneBase(next));
}

function cloneBase(next: BaseConfig): BaseConfig {
  return JSON.parse(JSON.stringify(next)) as BaseConfig;
}

async function loadSettings() {
  loading.value = true;
  try {
    profile.value = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    assignBase(profile.value.base);
  } catch (error) {
    console.error("load settings failed:", error);
    message.error("加载配置失败");
  } finally {
    loading.value = false;
  }
}

async function persistSettings() {
  if (!profile.value) return;
  saving.value = true;
  try {
    const next = cloneProfile(profile.value);
    next.base = cloneBase(base);
    next.meta.updated_at = new Date().toISOString();
    await saveProfile(DEFAULT_PROFILE_NAME, next);
    profile.value = next;
    message.success("配置已保存");
  } catch (error) {
    console.error("save settings failed:", error);
    message.error("保存配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(() => loadSettings());
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">基础配置</h1>
      <n-button size="small" type="primary" :loading="saving" @click="persistSettings">
        <template #icon><IconDeviceFloppy /></template>
        保存
      </n-button>
    </div>

    <n-alert v-if="loading" type="info" class="mb-4">正在加载配置...</n-alert>

    <n-space vertical size="large">
      <n-card title="用户界面">
        <n-space vertical>
          <n-text>主题</n-text>
          <n-input v-model:value="base.ui.theme" placeholder="darkly" />
        </n-space>
      </n-card>

      <n-card title="截屏与取色">
        <n-space vertical>
          <n-text>显示器策略</n-text>
          <n-input v-model:value="base.capture.monitor_policy" placeholder="primary" />
          <n-space align="center">
            <n-text>取色时避让鼠标</n-text>
            <n-switch v-model:value="base.pick.mouse_avoid" />
          </n-space>
          <n-text>避让偏移 Y</n-text>
          <n-input-number v-model:value="base.pick.mouse_avoid_offset_y" :min="-1000" :max="1000" />
          <n-text>避让稳定等待(ms)</n-text>
          <n-input-number v-model:value="base.pick.mouse_avoid_settle_ms" :min="0" :max="5000" />
        </n-space>
      </n-card>

      <n-card title="读条与完成检测">
        <n-space vertical>
          <n-text>模式</n-text>
          <n-input v-model:value="base.cast_bar.mode" placeholder="timer" />
          <n-text>读条点位 ID</n-text>
          <n-input v-model:value="base.cast_bar.point_id" placeholder="可选" />
          <n-text>容差</n-text>
          <n-input-number v-model:value="base.cast_bar.tolerance" :min="0" :max="255" />
          <n-text>轮询间隔(ms)</n-text>
          <n-input-number v-model:value="base.cast_bar.poll_interval_ms" :min="1" :max="10000" />
          <n-text>最大等待倍率</n-text>
          <n-input-number v-model:value="base.cast_bar.max_wait_factor" :min="0.1" :max="10" :step="0.1" />
        </n-space>
      </n-card>

      <n-card title="执行设置">
        <n-space vertical>
          <n-space align="center">
            <n-text>启用宏</n-text>
            <n-switch v-model:value="base.exec.enabled" />
          </n-space>
          <n-text>启停热键</n-text>
          <n-input v-model:value="base.exec.toggle_hotkey" placeholder="如 F9" />
          <n-text>技能间隔(ms)</n-text>
          <n-input-number v-model:value="base.exec.default_skill_gap_ms" :min="0" :max="10000" />
          <n-text>未就绪轮询(ms)</n-text>
          <n-input-number v-model:value="base.exec.poll_not_ready_ms" :min="1" :max="10000" />
          <n-text>最大重试次数</n-text>
          <n-input-number v-model:value="base.exec.max_retries" :min="0" :max="20" />
          <n-text>重试间隔(ms)</n-text>
          <n-input-number v-model:value="base.exec.retry_gap_ms" :min="0" :max="10000" />
        </n-space>
      </n-card>
    </n-space>
  </div>
</template>
