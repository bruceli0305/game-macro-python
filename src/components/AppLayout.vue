<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref, type Component } from "vue";
import { useRouter, useRoute } from "vue-router";
import {
  NButton,
  NIcon,
  NInput,
  NLayout,
  NLayoutContent,
  NLayoutSider,
  NMenu,
  NModal,
  NSelect,
  useMessage,
} from "naive-ui";
import {
  IconArrowsShuffle,
  IconKeyboard,
  IconPlayerPlay,
  IconPlus,
  IconPointer,
  IconSettings,
  IconSparkles,
} from "@tabler/icons-vue";
import {
  cloneProfile,
  createDefaultProfile,
  profileChangedEvent,
  useProfile,
} from "../composables/useProfile";
import {
  buildRoleProfileTemplate,
  isRoleProfileTemplateId,
  roleProfileTemplateLabel,
  roleProfileTemplateOptions,
} from "../utils/role-profile-templates";
import type { MenuOption, SelectOption } from "naive-ui";
import type { Profile } from "../types/profile";

type AppMessagePayload = {
  type?: "success" | "error" | "warning" | "info";
  content?: string;
};

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
const message = useMessage();
const {
  listProfiles,
  getActiveProfileName,
  setActiveProfileName,
  loadProfile,
  loadActiveProfile,
  saveProfile,
} = useProfile();

const collapsed = ref(false);
const currentKey = ref((route.name as string) || "settings");
const profileNames = ref<string[]>([]);
const activeProfileName = ref("default");
const profileLoading = ref(false);
const showCreateProfile = ref(false);
const newProfileName = ref("");

const profileOptions = computed<SelectOption[]>(() => [
  ...profileNames.value.map((name) => ({
    label: isRoleProfileTemplateId(name) ? roleProfileTemplateLabel(name) : name,
    value: name,
  })),
  ...roleProfileTemplateOptions
    .filter((option) => !profileNames.value.includes(option.id))
    .map((option) => ({
      label: `${option.label}（内置）`,
      value: option.id,
    })),
]);

function onMenuUpdate(key: string) {
  currentKey.value = key;
  router.push({ name: key });
}

async function refreshProfiles() {
  const [profiles, active] = await Promise.all([
    listProfiles(),
    getActiveProfileName(),
  ]);
  profileNames.value = profiles.map((profile) => profile.name);
  activeProfileName.value = active;
}

async function switchProfile(name: string) {
  if (!name || name === activeProfileName.value) return;

  profileLoading.value = true;
  try {
    if (!profileNames.value.includes(name) && isRoleProfileTemplateId(name)) {
      await saveProfile(name, buildRoleProfileTemplate(name));
      await refreshProfiles();
    }
    await setActiveProfileName(name);
    await loadProfile(name);
    activeProfileName.value = name;
    window.dispatchEvent(profileChangedEvent(name));
    window.dispatchEvent(new CustomEvent("hotkeys:reload"));
    message.success(`已切换角色配置：${name}`);
  } catch (error) {
    console.error("switch profile failed:", error);
    message.error(String(error || "切换角色配置失败"));
  } finally {
    profileLoading.value = false;
  }
}

function profileWithName(profile: Profile, name: string): Profile {
  const next = cloneProfile(profile);
  const now = new Date().toISOString();
  next.meta.profile_id = name;
  next.meta.profile_name = name;
  next.meta.created_at = now;
  next.meta.updated_at = now;
  return next;
}

async function createProfile(copyCurrent: boolean) {
  const name = newProfileName.value.trim();
  if (!name) {
    message.error("角色配置 ID 不能为空");
    return;
  }
  if (profileNames.value.includes(name)) {
    message.error(`角色配置已存在：${name}`);
    return;
  }

  if (isRoleProfileTemplateId(name)) {
    message.error("This ID is a built-in role profile. Select it from the profile dropdown.");
    return;
  }

  profileLoading.value = true;
  try {
    const profile = copyCurrent
      ? profileWithName(await loadActiveProfile(), name)
      : createDefaultProfile(name);
    await saveProfile(name, profile);
    await refreshProfiles();
    await switchProfile(name);
    newProfileName.value = "";
    showCreateProfile.value = false;
  } catch (error) {
    console.error("create profile failed:", error);
    message.error(String(error || "创建角色配置失败"));
  } finally {
    profileLoading.value = false;
  }
}

function onAppMessage(event: Event) {
  const detail = (event as CustomEvent<AppMessagePayload>).detail;
  const content = detail?.content?.trim();
  if (!content) return;

  switch (detail.type) {
    case "success":
      message.success(content);
      break;
    case "warning":
      message.warning(content);
      break;
    case "info":
      message.info(content);
      break;
    case "error":
    default:
      message.error(content);
      break;
  }
}

onMounted(() => {
  window.addEventListener("app:message", onAppMessage);
  void refreshProfiles();
});

onUnmounted(() => window.removeEventListener("app:message", onAppMessage));
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
      <div class="flex items-center gap-2 border-b border-white/10 p-4">
        <n-icon size="24" color="#18a058">
          <IconKeyboard />
        </n-icon>
        <span v-if="!collapsed" class="truncate text-sm font-semibold">宏工具</span>
      </div>

      <div v-if="!collapsed" class="border-b border-white/10 p-3">
        <div class="mb-1 text-xs text-gray-400">角色配置</div>
        <div class="flex items-center gap-1">
          <n-select
            :value="activeProfileName"
            size="small"
            :options="profileOptions"
            :loading="profileLoading"
            @update:value="switchProfile"
          />
          <n-button size="small" secondary :loading="profileLoading" @click="showCreateProfile = true">
            <template #icon>
              <IconPlus />
            </template>
          </n-button>
        </div>
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
      <div class="h-full overflow-auto p-4">
        <router-view />
      </div>
    </n-layout-content>
  </n-layout>

  <n-modal v-model:show="showCreateProfile" preset="dialog" title="新建角色配置">
    <div class="flex flex-col gap-3">
      <n-input v-model:value="newProfileName" placeholder="profile_id，例如 power_virtuoso" />
      <div class="text-xs text-gray-400">
        ID 仅支持字母、数字、下划线和短横线。
      </div>
      <div class="flex justify-end gap-2">
        <n-button size="small" @click="showCreateProfile = false">取消</n-button>
        <n-button size="small" :loading="profileLoading" @click="createProfile(false)">
          创建空配置
        </n-button>
        <n-button size="small" type="primary" :loading="profileLoading" @click="createProfile(true)">
          复制当前配置
        </n-button>
      </div>
    </div>
  </n-modal>
</template>
