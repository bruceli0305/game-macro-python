<script setup lang="ts">
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import {
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NIcon,
} from "naive-ui";
import {
  IconSettings,
  IconSparkles,
  IconPointer,
  IconArrowsShuffle,
  IconPlayerPlay,
  IconKeyboard,
} from "@tabler/icons-vue";
import type { MenuOption } from "naive-ui";
import { h, type Component } from "vue";

function renderIcon(icon: Component) {
  return () => h(NIcon, null, { default: () => h(icon) });
}

const menuOptions: MenuOption[] = [
  { label: "基础配置", key: "settings", icon: renderIcon(IconSettings) },
  { label: "技能管理", key: "skills", icon: renderIcon(IconSparkles) },
  { label: "点位管理", key: "points", icon: renderIcon(IconPointer) },
  { label: "循环编辑器", key: "cycle-editor", icon: renderIcon(IconArrowsShuffle) },
  { label: "离线推演", key: "simulator", icon: renderIcon(IconPlayerPlay) },
];

const router = useRouter();
const route = useRoute();
const collapsed = ref(false);

const currentKey = ref((route.name as string) || "settings");

function onMenuUpdate(key: string) {
  currentKey.value = key;
  router.push({ name: key });
}
</script>

<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="200"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="flex items-center gap-2 p-4 border-b border-white/10">
        <n-icon size="24" color="#18a058">
          <IconKeyboard />
        </n-icon>
        <span v-if="!collapsed" class="text-sm font-semibold truncate">宏工具</span>
      </div>
      <n-menu
        :value="currentKey"
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        @update:value="onMenuUpdate"
      />
    </n-layout-sider>

    <n-layout-content>
      <div class="p-4 h-full overflow-auto">
        <router-view />
      </div>
    </n-layout-content>
  </n-layout>
</template>
