// Skill IPC wrappers.

import { invoke } from "@tauri-apps/api/core";

export interface Gw2SkillInfo {
  id: number;
  name: string;
  description: string;
  cooldown_ms: number;
  radius: number;
}

export function useSkill() {
  async function searchGw2Skills(query: string): Promise<Gw2SkillInfo[]> {
    return await invoke<Gw2SkillInfo[]>("gw2_skill_search", { query });
  }

  return { searchGw2Skills };
}
