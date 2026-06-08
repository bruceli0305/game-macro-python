<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import {
  NConfigProvider,
  NMessageProvider,
  darkTheme,
  zhCN,
  dateZhCN,
} from "naive-ui";
import AppLayout from "./components/AppLayout.vue";
import { useHotkeys } from "./composables/useHotkeys";

const { setup, teardown, reload } = useHotkeys();

function reloadHotkeys() {
  void reload();
}

onMounted(() => {
  void setup();
  window.addEventListener("hotkeys:reload", reloadHotkeys);
});

onUnmounted(() => {
  window.removeEventListener("hotkeys:reload", reloadHotkeys);
  void teardown();
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <AppLayout />
    </n-message-provider>
  </n-config-provider>
</template>
