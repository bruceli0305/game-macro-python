// Profile IPC 封装 — 接入 Tauri invoke

import { invoke } from "@tauri-apps/api/core";
import { useProfileStore } from "../stores/profile";
import type { CycleConfig } from "../types/cycle";
import type { Point } from "../types/point";
import type { Profile } from "../types/profile";
import type { Skill } from "../types/skill";

export const DEFAULT_PROFILE_NAME = "default";

export interface ProfileInfo {
  name: string;
}

export interface ActiveProfileInfo {
  name: string;
}

export function createDefaultProfile(name = DEFAULT_PROFILE_NAME): Profile {
  const now = new Date().toISOString();

  return {
    schema_version: 1,
    meta: {
      profile_id: name,
      profile_name: name,
      created_at: now,
      updated_at: now,
      description: "",
    },
    base: {
      schema_version: 2,
      ui: { theme: "darkly" },
      capture: { monitor_policy: "primary" },
      pick: {
        confirm_hotkey: "F8",
        mouse_avoid: true,
        mouse_avoid_offset_y: 80,
        mouse_avoid_settle_ms: 80,
      },
      io: { backup_on_save: false },
      cast_bar: {
        mode: "timer",
        point_id: "",
        tolerance: 15,
        poll_interval_ms: 30,
        max_wait_factor: 1.5,
        roi: {
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
        },
      },
      exec: {
        enabled: false,
        toggle_hotkey: "F9",
        default_skill_gap_ms: 50,
        poll_not_ready_ms: 50,
        max_retries: 3,
        retry_gap_ms: 30,
      },
    },
    skills: { schema_version: 2, skills: [] },
    points: { schema_version: 3, points: [] },
    rotations: [],
  };
}

export function cloneProfile(profile: Profile): Profile {
  return JSON.parse(JSON.stringify(profile)) as Profile;
}

export function profileChangedEvent(name: string): CustomEvent<{ name: string }> {
  return new CustomEvent("profile:active-changed", { detail: { name } });
}

function hasTauriRuntime(): boolean {
  if (typeof window === "undefined") return false;
  const tauri = (window as Window & {
    __TAURI_INTERNALS__?: { invoke?: unknown };
  }).__TAURI_INTERNALS__;
  return typeof tauri?.invoke === "function";
}

export function withProfileSkills(profile: Profile, skills: Skill[]): Profile {
  const next = cloneProfile(profile);
  next.skills = { schema_version: 2, skills };
  next.meta.updated_at = new Date().toISOString();
  return next;
}

export function withProfilePoints(profile: Profile, points: Point[]): Profile {
  const next = cloneProfile(profile);
  next.points = { schema_version: 3, points };
  next.meta.updated_at = new Date().toISOString();
  return next;
}

export function withProfileRotations(profile: Profile, rotations: CycleConfig[]): Profile {
  const next = cloneProfile(profile);
  next.rotations = rotations;
  next.meta.updated_at = new Date().toISOString();
  return next;
}

export function useProfile() {
  const store = useProfileStore();

  async function listProfiles(): Promise<ProfileInfo[]> {
    if (!hasTauriRuntime()) {
      const names = new Set<string>([store.activeProfileName || DEFAULT_PROFILE_NAME]);
      const profileId = store.profile?.meta?.profile_id?.trim();
      if (profileId) names.add(profileId);
      return [...names].map((name) => ({ name }));
    }
    return await invoke<ProfileInfo[]>("profile_list");
  }

  async function getActiveProfileName(): Promise<string> {
    if (!hasTauriRuntime()) {
      store.activeProfileName ||= DEFAULT_PROFILE_NAME;
      return store.activeProfileName;
    }
    const active = await invoke<ActiveProfileInfo>("profile_get_active");
    store.activeProfileName = active.name || DEFAULT_PROFILE_NAME;
    return store.activeProfileName;
  }

  async function setActiveProfileName(name: string): Promise<void> {
    if (hasTauriRuntime()) {
      await invoke("profile_set_active", { name });
    }
    store.activeProfileName = name;
  }

  async function loadProfile(name: string): Promise<Profile> {
    if (!hasTauriRuntime()) {
      const profile = store.profile && store.activeProfileName === name
        ? cloneProfile(store.profile)
        : createDefaultProfile(name);
      store.profile = profile;
      store.activeProfileName = name;
      return profile;
    }
    const content = await invoke<string>("profile_load", { name });
    const profile = JSON.parse(content) as Profile;
    store.profile = profile;
    store.activeProfileName = name;
    return profile;
  }

  async function loadOrCreateProfile(name = DEFAULT_PROFILE_NAME): Promise<Profile> {
    try {
      return await loadProfile(name);
    } catch {
      const profile = createDefaultProfile(name);
      store.profile = profile;
      return profile;
    }
  }

  async function loadActiveProfile(): Promise<Profile> {
    const name = await getActiveProfileName();
    return await loadOrCreateProfile(name);
  }

  async function saveProfile(name: string, profile: Profile): Promise<void> {
    const content = JSON.stringify(profile, null, 2);
    if (hasTauriRuntime()) {
      await invoke("profile_save", { name, content });
    }
    store.profile = cloneProfile(profile);
    store.clearAllDirty();
  }

  async function saveActiveProfile(profile: Profile): Promise<void> {
    const name = store.activeProfileName || (await getActiveProfileName());
    await saveProfile(name, profile);
  }

  async function saveSkills(name: string, skills: Skill[]): Promise<Profile> {
    const profile = withProfileSkills(await loadOrCreateProfile(name), skills);
    await saveProfile(name, profile);
    return profile;
  }

  async function savePoints(name: string, points: Point[]): Promise<Profile> {
    const profile = withProfilePoints(await loadOrCreateProfile(name), points);
    await saveProfile(name, profile);
    return profile;
  }

  async function saveRotations(name: string, rotations: CycleConfig[]): Promise<Profile> {
    const profile = withProfileRotations(await loadOrCreateProfile(name), rotations);
    await saveProfile(name, profile);
    return profile;
  }

  return {
    listProfiles,
    getActiveProfileName,
    setActiveProfileName,
    loadProfile,
    loadOrCreateProfile,
    loadActiveProfile,
    saveProfile,
    saveActiveProfile,
    saveSkills,
    savePoints,
    saveRotations,
    store,
  };
}
