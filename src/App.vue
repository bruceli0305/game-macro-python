<script setup lang="ts">
import { onMounted } from "vue";
import { darkTheme, zhCN, dateZhCN } from "naive-ui";
import AppLayout from "./components/AppLayout.vue";
import { useHotkeys } from "./composables/useHotkeys";

const { setup } = useHotkeys();
onMounted(() => setup());
</script>

<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <AppLayout />
    </n-message-provider>
  </n-config-provider>
</template>
