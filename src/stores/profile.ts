import { defineStore } from "pinia";
import { ref } from "vue";
import type { Profile } from "../types/profile";

export const useProfileStore = defineStore("profile", () => {
  const profile = ref<Profile | null>(null);
  const dirtyFlags = ref<Set<string>>(new Set());

  function markDirty(part: string) {
    dirtyFlags.value.add(part);
  }

  function clearDirty(part: string) {
    dirtyFlags.value.delete(part);
  }

  function clearAllDirty() {
    dirtyFlags.value.clear();
  }

  function isDirty() {
    return dirtyFlags.value.size > 0;
  }

  return { profile, dirtyFlags, markDirty, clearDirty, clearAllDirty, isDirty };
});
