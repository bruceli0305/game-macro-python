// 与 Rust models/skill.rs 对齐

export interface ColorRGB { r: number; g: number; b: number }
export interface SampleConfig { mode: string; radius: number }

export interface PixelSpec {
  monitor: string;
  vx: number;
  vy: number;
  color: ColorRGB;
  tolerance: number;
  sample: SampleConfig;
}

export interface CastConfig {
  readbar_ms: number;
  cooldown_ms: number;
}

export interface AmmoStagePixel {
  charges_left: number;
  pixel: PixelSpec;
}

export interface Skill {
  id: string;
  name: string;
  enabled: boolean;
  trigger_key: string;
  cast: CastConfig;
  pixel: PixelSpec;
  note: string;
  game_id: number;
  game_desc: string;
  icon_url: string;
  cooldown_ms: number;
  radius: number;
  shots_per_cycle: number;
  ammo_stages: AmmoStagePixel[];
}

export interface SkillsFile {
  schema_version: number;
  skills: Skill[];
}
