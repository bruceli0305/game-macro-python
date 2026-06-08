<script setup lang="ts">
import { ref } from "vue";
import { NModal, NCard, NButton, NSpace } from "naive-ui";
import { IconPointer } from "@tabler/icons-vue";
import { useCapture } from "../../composables/useCapture";

const show = ref(false);
const color = ref({ r: 0, g: 0, b: 0 });
const hex = ref("#000000");
const pos = ref({ monitor: "primary", x: 0, y: 0 });
const loading = ref(false);
const { captureAtCursor } = useCapture();

async function startPicking() {
  show.value = true;
  await refreshAtCursor();
}

async function refreshAtCursor() {
  loading.value = true;
  try {
    const result = await captureAtCursor();
    if (!result) return;
    color.value = { r: result.r, g: result.g, b: result.b };
    hex.value = result.hex;
    pos.value = { monitor: result.monitor, x: result.x, y: result.y };
  } finally {
    loading.value = false;
  }
}

function stopPicking() {
  show.value = false;
}
</script>

<template>
  <n-button size="small" @click="startPicking">
    <template #icon><IconPointer /></template>
    取色
  </n-button>

  <n-modal :show="show" :mask-closable="false" @update:show="stopPicking">
    <n-card title="像素取色" size="small" style="width:320px" closable @close="stopPicking">
      <!-- 颜色预览 -->
      <div class="flex items-center gap-4 mb-4">
        <div
          class="w-16 h-16 rounded border border-white/20 shadow-lg"
          :style="{ backgroundColor: hex }"
        />
        <div>
          <div class="text-lg font-mono">{{ hex }}</div>
          <div class="text-sm text-gray-400">R:{{ color.r }} G:{{ color.g }} B:{{ color.b }}</div>
          <div class="text-xs text-gray-500">显示器: {{ pos.monitor }}</div>
          <div class="text-xs text-gray-500">位置: ({{ pos.x }}, {{ pos.y }})</div>
        </div>
      </div>

      <!-- 放大预览区域 -->
      <div class="relative w-full h-32 rounded overflow-hidden border border-white/10 bg-black/30">
        <div class="absolute inset-0 flex items-center justify-center">
          <div
            class="w-8 h-8 rounded-full border-2 border-white shadow-lg"
            :style="{ backgroundColor: hex }"
          />
          <div class="absolute text-xs text-white/50 bottom-1">十字线中心为采样点</div>
        </div>
      </div>

      <n-space justify="end" class="mt-4">
        <n-button :loading="loading" @click="refreshAtCursor">刷新当前鼠标像素</n-button>
        <n-button @click="stopPicking">关闭</n-button>
      </n-space>
    </n-card>
  </n-modal>
</template>
