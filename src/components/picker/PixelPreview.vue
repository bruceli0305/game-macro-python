<script setup lang="ts">
import { ref, onUnmounted } from "vue";
import { NModal, NCard, NButton, NSpace } from "naive-ui";
import { IconPointer } from "@tabler/icons-vue";

const show = ref(false);
const color = ref({ r: 0, g: 0, b: 0 });
const hex = ref("#000000");
const pos = ref({ x: 0, y: 0 });
let timer: ReturnType<typeof setInterval> | null = null;

async function startPicking() {
  show.value = true;
  // 每 100ms 采样一次鼠标位置像素
  timer = setInterval(async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      // 使用 Tauri 的 cursor position API 或直接传固定坐标
      // 当前简化：采样屏幕中心附近
      const x = 500 + Math.floor(Math.random() * 200);
      const y = 500 + Math.floor(Math.random() * 200);
      const [r, g, b] = await invoke<[number, number, number]>("capture_sample", { x, y });
      color.value = { r, g, b };
      hex.value = `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
      pos.value = { x, y };
    } catch (e) {
      console.error("采样失败:", e);
    }
  }, 100);
}

function stopPicking() {
  if (timer) { clearInterval(timer); timer = null; }
  show.value = false;
}

onUnmounted(() => { if (timer) clearInterval(timer); });
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
        <n-button @click="stopPicking">关闭</n-button>
      </n-space>
    </n-card>
  </n-modal>
</template>
