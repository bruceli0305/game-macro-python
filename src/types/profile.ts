// 与 Rust models/profile.rs 对齐

export interface ProfileMeta {
  profile_id: string;
  profile_name: string;
  created_at: string;
  updated_at: string;
  description: string;
}

export interface Profile {
  schema_version: number;
  meta: ProfileMeta;
  base: BaseConfig;
  skills: SkillsFile;
  points: PointsFile;
  rotations: CycleConfig[];
}

export interface BaseConfig {
  schema_version: number;
  ui: UiConfig;
  capture: CaptureConfig;
  pick: PickConfig;
  io: IoConfig;
  cast_bar: CastBarConfig;
  exec: ExecConfig;
}

export interface UiConfig { theme: string }
export interface CaptureConfig { monitor_policy: string }
export interface PickConfig {
  confirm_hotkey: string;
  mouse_avoid: boolean;
  mouse_avoid_offset_y: number;
  mouse_avoid_settle_ms: number;
}
export interface IoConfig { auto_save: boolean; backup_on_save: boolean }
export interface CastBarConfig {
  mode: string;
  point_id: string;
  tolerance: number;
  poll_interval_ms: number;
  max_wait_factor: number;
  roi: CastBarRoiConfig;
}
export interface CastBarRoiConfig {
  enabled: boolean;
  monitor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  baseline_color: ColorRGB;
  diff_threshold: number;
  min_changed_ratio: number;
  border_enabled: boolean;
  border_color: ColorRGB;
  border_tolerance: number;
  min_border_match_ratio: number;
  confirm_frames: number;
}
export interface ExecConfig {
  enabled: boolean;
  toggle_hotkey: string;
  default_skill_gap_ms: number;
  poll_not_ready_ms: number;
  max_retries: number;
  retry_gap_ms: number;
}

import type { Skill, SkillsFile, ColorRGB, PixelSpec, CastConfig, AmmoStagePixel } from "./skill";
import type { Point, PointsFile } from "./point";
import type { CycleConfig, CyclePhase, SkillSlot } from "./cycle";

export type { Skill, SkillsFile, ColorRGB, PixelSpec, CastConfig, AmmoStagePixel };
export type { Point, PointsFile };
export type { CycleConfig, CyclePhase, SkillSlot };
