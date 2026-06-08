<script setup lang="ts">
import { NButton, NSpace, NTag } from "naive-ui";
import { IconPlayerPlay, IconPlayerStop } from "@tabler/icons-vue";
import { useEngine } from "../../composables/useEngine";

const { start, stop, store } = useEngine();
</script>

<template>
  <n-space align="center">
    <n-button
      v-if="!store.isRunning"
      type="success"
      @click="start()"
    >
      <template #icon><IconPlayerPlay /></template>
      启动
    </n-button>

    <n-button
      v-if="store.isRunning"
      type="error"
      @click="stop()"
    >
      <template #icon><IconPlayerStop /></template>
      停止
    </n-button>

    <n-tag v-if="store.isRunning" type="success" size="small">运行中</n-tag>
    <n-tag v-else type="default" size="small">已停止</n-tag>

    <span v-if="store.isRunning" class="text-xs text-gray-400">
      Phase {{ store.currentPhase + 1 }} · 循环 {{ store.cycleCount }}
    </span>
  </n-space>
</template>
