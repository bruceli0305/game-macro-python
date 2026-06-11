<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
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
const route = useRoute();
const router = useRouter();

function reloadHotkeys() {
  void reload();
}

onMounted(() => {
  if (window.location.search.includes("debugPanel=1")) {
    void router.replace({ name: "debug-panel" });
    return;
  }
  if (route.name === "debug-panel") return;
  void setup();
  window.addEventListener("hotkeys:reload", reloadHotkeys);
});

onUnmounted(() => {
  if (route.name === "debug-panel") return;
  window.removeEventListener("hotkeys:reload", reloadHotkeys);
  void teardown();
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <router-view v-if="route.name === 'debug-panel'" />
      <AppLayout v-else />
    </n-message-provider>
  </n-config-provider>
</template>
