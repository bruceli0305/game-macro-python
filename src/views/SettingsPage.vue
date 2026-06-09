<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSwitch,
  NText,
  useMessage,
} from "naive-ui";
import { IconDeviceFloppy } from "@tabler/icons-vue";
import ProfileIssueSummary from "../components/common/ProfileIssueSummary.vue";
import { useCapture, type CastBarRoiSample } from "../composables/useCapture";
import { DEFAULT_PROFILE_NAME, cloneProfile, useProfile } from "../composables/useProfile";
import { firstProfileError, validateProfileForSave } from "../utils/profile-validation";
import type { BaseConfig, CastBarRoiConfig, Profile } from "../types/profile";
import type { ColorRGB } from "../types/skill";

const message = useMessage();
const { loadOrCreateProfile, saveProfile } = useProfile();
const { captureAtCursor, captureCastBarRoi } = useCapture();
const loading = ref(false);
const saving = ref(false);
const profile = ref<Profile | null>(null);
const roiTesting = ref(false);
const roiSample = ref<CastBarRoiSample | null>(null);
const castBarModeOptions = [
  { label: "计时模式", value: "timer" },
  { label: "像素读条", value: "pixel" },
  { label: "施法条 ROI", value: "roi" },
];

function defaultCastBarRoi(): CastBarRoiConfig {
  return {
    enabled: false,
    monitor: "primary",
    x: 0,
    y: 0,
    width: 0,
    height: 0,
    baseline_color: { r: 0, g: 0, b: 0 },
    diff_threshold: 18,
    min_changed_ratio: 0.08,
    border_enabled: false,
    border_color: { r: 0, g: 0, b: 0 },
    border_tolerance: 24,
    min_border_match_ratio: 0.2,
    confirm_frames: 2,
  };
}

function cloneColor(value: Partial<ColorRGB> | null | undefined): ColorRGB {
  return {
    r: Number.isFinite(value?.r) ? Number(value?.r) : 0,
    g: Number.isFinite(value?.g) ? Number(value?.g) : 0,
    b: Number.isFinite(value?.b) ? Number(value?.b) : 0,
  };
}

function normalizeCastBarRoi(value: Partial<CastBarRoiConfig> | null | undefined): CastBarRoiConfig {
  const fallback = defaultCastBarRoi();
  return {
    ...fallback,
    ...(value ?? {}),
    baseline_color: cloneColor(value?.baseline_color ?? fallback.baseline_color),
    border_color: cloneColor(value?.border_color ?? fallback.border_color),
  };
}

const base = reactive<BaseConfig>({
  schema_version: 2,
  ui: { theme: "darkly" },
  capture: { monitor_policy: "primary" },
  pick: {
    confirm_hotkey: "F8",
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
    roi: defaultCastBarRoi(),
  },
  exec: {
    enabled: false,
    toggle_hotkey: "F9",
    default_skill_gap_ms: 50,
    poll_not_ready_ms: 50,
    max_retries: 3,
    retry_gap_ms: 30,
  },
});

function assignBase(next: BaseConfig) {
  const cloned = cloneBase(next);
  if (!cloned.pick.confirm_hotkey.trim()) cloned.pick.confirm_hotkey = "F8";
  if (!cloned.exec.toggle_hotkey.trim()) cloned.exec.toggle_hotkey = "F9";
  cloned.cast_bar.roi = normalizeCastBarRoi(cloned.cast_bar.roi);
  Object.assign(base, cloned);
}

function cloneBase(next: BaseConfig): BaseConfig {
  return JSON.parse(JSON.stringify(next)) as BaseConfig;
}

const settingsIssues = computed(() => {
  if (!profile.value) return [];
  const next = cloneProfile(profile.value);
  next.base = cloneBase(base);
  return validateProfileForSave(next);
});

function roiRequest() {
  const roi = base.cast_bar.roi;
  return {
    monitor: roi.monitor,
    x: roi.x,
    y: roi.y,
    width: roi.width,
    height: roi.height,
    baseline_color: roi.baseline_color,
    diff_threshold: roi.diff_threshold,
    min_changed_ratio: roi.min_changed_ratio,
    border_enabled: roi.border_enabled,
    border_color: roi.border_color,
    border_tolerance: roi.border_tolerance,
    min_border_match_ratio: roi.min_border_match_ratio,
  };
}

function formatColor(color: ColorRGB): string {
  return `#${color.r.toString(16).padStart(2, "0")}${color.g.toString(16).padStart(2, "0")}${color.b.toString(16).padStart(2, "0")}`.toUpperCase();
}

function formatRatio(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

async function setRoiTopLeftFromCursor() {
  const sample = await captureAtCursor();
  if (!sample) {
    message.error("读取鼠标位置失败");
    return;
  }
  base.cast_bar.roi.monitor = sample.monitor;
  base.cast_bar.roi.x = sample.x;
  base.cast_bar.roi.y = sample.y;
  roiSample.value = null;
  message.success("已设置 ROI 左上角");
}

async function setRoiBottomRightFromCursor() {
  const sample = await captureAtCursor();
  if (!sample) {
    message.error("读取鼠标位置失败");
    return;
  }
  base.cast_bar.roi.monitor = sample.monitor;
  base.cast_bar.roi.width = Math.max(1, sample.x - base.cast_bar.roi.x);
  base.cast_bar.roi.height = Math.max(1, sample.y - base.cast_bar.roi.y);
  roiSample.value = null;
  message.success("已设置 ROI 右下角");
}

async function testCastBarRoi(updateBaseline: boolean) {
  roiTesting.value = true;
  try {
    const sample = await captureCastBarRoi(roiRequest());
    if (!sample) {
      message.error("ROI 检测失败");
      return;
    }
    roiSample.value = sample;
    if (updateBaseline) {
      base.cast_bar.roi.baseline_color = { ...sample.average_color };
      message.success("已采样 ROI 基准色");
    } else {
      message.success("ROI 检测完成");
    }
  } finally {
    roiTesting.value = false;
  }
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
    const error = firstProfileError(validateProfileForSave(next));
    if (error) {
      message.error(error);
      return;
    }
    await saveProfile(DEFAULT_PROFILE_NAME, next);
    profile.value = next;
    window.dispatchEvent(new CustomEvent("hotkeys:reload"));
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

    <ProfileIssueSummary
      :issues="settingsIssues"
      title="保存检查"
      :limit="6"
    />

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
          <n-text>取色确认热键</n-text>
          <n-input v-model:value="base.pick.confirm_hotkey" placeholder="F8" />
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
          <n-select v-model:value="base.cast_bar.mode" :options="castBarModeOptions" />
          <n-text>读条点位 ID</n-text>
          <n-input v-model:value="base.cast_bar.point_id" placeholder="可选" />
          <n-text>容差</n-text>
          <n-input-number v-model:value="base.cast_bar.tolerance" :min="0" :max="255" />
          <n-text>轮询间隔(ms)</n-text>
          <n-input-number v-model:value="base.cast_bar.poll_interval_ms" :min="1" :max="10000" />
          <n-text>最大等待倍率</n-text>
          <n-input-number v-model:value="base.cast_bar.max_wait_factor" :min="0.1" :max="10" :step="0.1" />

          <n-space align="center" class="pt-2">
            <n-text>启用施法条 ROI 检测</n-text>
            <n-switch v-model:value="base.cast_bar.roi.enabled" />
          </n-space>
          <n-alert type="info" :bordered="false">
            ROI 检测只读取屏幕截图中的矩形区域，可利用 Castbar Clarity 强化后的边框和颜色变化判断施法条是否出现。
          </n-alert>

          <n-space align="center" wrap>
            <n-button size="small" secondary @click="setRoiTopLeftFromCursor">
              鼠标设为左上角
            </n-button>
            <n-button size="small" secondary @click="setRoiBottomRightFromCursor">
              鼠标设为右下角
            </n-button>
            <n-button size="small" :loading="roiTesting" @click="testCastBarRoi(true)">
              采样基准
            </n-button>
            <n-button size="small" type="primary" secondary :loading="roiTesting" @click="testCastBarRoi(false)">
              测试 ROI
            </n-button>
          </n-space>

          <n-space wrap>
            <n-space vertical size="small">
              <n-text>ROI 显示器</n-text>
              <n-input v-model:value="base.cast_bar.roi.monitor" placeholder="primary" style="width: 180px" />
            </n-space>
            <n-space vertical size="small">
              <n-text>X</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.x" :min="-10000" :max="10000" />
            </n-space>
            <n-space vertical size="small">
              <n-text>Y</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.y" :min="-10000" :max="10000" />
            </n-space>
            <n-space vertical size="small">
              <n-text>宽度</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.width" :min="0" :max="2000" />
            </n-space>
            <n-space vertical size="small">
              <n-text>高度</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.height" :min="0" :max="500" />
            </n-space>
          </n-space>

          <n-space wrap>
            <n-space vertical size="small">
              <n-text>基准色 R</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.baseline_color.r" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>基准色 G</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.baseline_color.g" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>基准色 B</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.baseline_color.b" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>帧差阈值</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.diff_threshold" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>最小变化比例</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.min_changed_ratio" :min="0" :max="1" :step="0.01" />
            </n-space>
            <n-space vertical size="small">
              <n-text>确认帧数</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.confirm_frames" :min="1" :max="10" />
            </n-space>
          </n-space>

          <n-space align="center">
            <n-text>检测 Castbar Clarity 边框色</n-text>
            <n-switch v-model:value="base.cast_bar.roi.border_enabled" />
          </n-space>
          <n-space wrap>
            <n-space vertical size="small">
              <n-text>边框 R</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.border_color.r" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>边框 G</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.border_color.g" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>边框 B</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.border_color.b" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>边框容差</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.border_tolerance" :min="0" :max="255" />
            </n-space>
            <n-space vertical size="small">
              <n-text>最小边框命中比例</n-text>
              <n-input-number v-model:value="base.cast_bar.roi.min_border_match_ratio" :min="0" :max="1" :step="0.01" />
            </n-space>
          </n-space>

          <n-alert v-if="roiSample" type="success" :bordered="false">
            ROI {{ roiSample.width }}x{{ roiSample.height }}，像素 {{ roiSample.pixel_count }}；
            平均色 {{ formatColor(roiSample.average_color) }}；
            变化比例 {{ formatRatio(roiSample.changed_ratio) }}
            <strong>{{ roiSample.changed_from_baseline ? "已变化" : "未变化" }}</strong>；
            边框命中 {{ formatRatio(roiSample.border_match_ratio) }}
            <strong>{{ roiSample.border_visible ? "可见" : "未命中" }}</strong>
          </n-alert>
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
