import roleProfileSeedData from "../assets/json/role-profile-seeds.json";
import { createDefaultProfile } from "../composables/useProfile";
import type { Profile } from "../types/profile";
import type { Point } from "../types/point";
import type { ColorRGB, PixelSpec, Skill } from "../types/skill";
import { buildCyclePreset, type CyclePresetId } from "./cycle-presets";

export type RoleProfileTemplateId =
  | "power_virtuoso_greatsword"
  | "condi_quickness_firebrand"
  | "condition_weaver_pistol_dagger";

export interface RoleProfileTemplateOption {
  id: RoleProfileTemplateId;
  label: string;
  description: string;
}

interface SkillSeed {
  id: string;
  name: string;
  key: string;
  x: number;
  y: number;
  color: string;
  readbarMs?: number;
  cooldownMs?: number;
  shots_per_cycle?: number;
  note?: string;
}

interface PointSeed {
  id: string;
  name: string;
  x: number;
  y: number;
  color: string;
  note?: string;
}

interface RoleProfileSeed {
  id: RoleProfileTemplateId;
  label: string;
  description: string;
  rotation_id: CyclePresetId;
  default_shots_per_cycle?: number;
  base?: BaseSeed;
  skills: SkillSeed[];
  points: PointSeed[];
}

interface BaseSeed {
  cast_bar?: Partial<Profile["base"]["cast_bar"]> & {
    roi?: Partial<Profile["base"]["cast_bar"]["roi"]>;
  };
  exec?: Partial<Profile["base"]["exec"]>;
}

interface RoleProfileSeedFile {
  schema_version: number;
  profiles: RoleProfileSeed[];
}

const seedFile = roleProfileSeedData as RoleProfileSeedFile;
const roleProfileSeeds = seedFile.profiles;

export const roleProfileTemplateOptions: RoleProfileTemplateOption[] = roleProfileSeeds.map(
  (seed) => ({
    id: seed.id,
    label: seed.label,
    description: seed.description,
  }),
);

const templateIds = new Set<string>(roleProfileTemplateOptions.map((option) => option.id));

export function isRoleProfileTemplateId(value: string): value is RoleProfileTemplateId {
  return templateIds.has(value);
}

export function roleProfileTemplateLabel(id: RoleProfileTemplateId): string {
  return roleSeedById(id).label;
}

export function buildRoleProfileTemplate(id: RoleProfileTemplateId): Profile {
  const seed = roleSeedById(id);
  const profile = createDefaultProfile(id);

  profile.meta.profile_name = seed.label;
  profile.meta.description = seed.description;
  profile.rotations = [buildCyclePreset(seed.rotation_id)];
  applyBaseSeed(profile, seed.base);
  profile.skills = {
    schema_version: 2,
    skills: seed.skills.map((item) => skill(item, seed.default_shots_per_cycle ?? 1)),
  };
  profile.points = { schema_version: 3, points: seed.points.map(point) };

  return profile;
}

function applyBaseSeed(profile: Profile, seed?: BaseSeed): void {
  if (!seed) return;

  if (seed.cast_bar) {
    profile.base.cast_bar = {
      ...profile.base.cast_bar,
      ...seed.cast_bar,
      roi: {
        ...profile.base.cast_bar.roi,
        ...seed.cast_bar.roi,
      },
    };
  }

  if (seed.exec) {
    profile.base.exec = {
      ...profile.base.exec,
      ...seed.exec,
    };
  }
}

function roleSeedById(id: RoleProfileTemplateId): RoleProfileSeed {
  const seed = roleProfileSeeds.find((item) => item.id === id);
  if (!seed) {
    throw new Error(`Missing built-in role profile seed: ${id}`);
  }
  return seed;
}

function rgb(hex: string): ColorRGB {
  const normalized = hex.trim().replace(/^0x/i, "").replace(/^#/, "").padStart(6, "0");
  const value = Number.parseInt(normalized, 16);
  return {
    r: (value >> 16) & 0xff,
    g: (value >> 8) & 0xff,
    b: value & 0xff,
  };
}

function pixel(x: number, y: number, color: string, tolerance = 24): PixelSpec {
  return {
    monitor: "primary",
    vx: x,
    vy: y,
    color: rgb(color),
    tolerance,
    sample: { mode: "single", radius: 0 },
  };
}

function skill(seed: SkillSeed, defaultShotsPerCycle: number): Skill {
  return {
    id: seed.id,
    name: seed.name,
    enabled: true,
    trigger_key: seed.key,
    cast: {
      readbar_ms: seed.readbarMs ?? 0,
      cooldown_ms: seed.cooldownMs ?? 0,
    },
    pixel: pixel(seed.x, seed.y, seed.color),
    note: seed.note ?? "Built-in role profile seed. Re-pick this pixel if UI scale changes.",
    game_id: 0,
    game_desc: "",
    icon_url: "",
    cooldown_ms: seed.cooldownMs ?? 0,
    radius: 0,
    shots_per_cycle: seed.shots_per_cycle ?? defaultShotsPerCycle,
    ammo_stages: [],
  };
}

function point(seed: PointSeed): Point {
  return {
    id: seed.id,
    name: seed.name,
    monitor: "primary",
    vx: seed.x,
    vy: seed.y,
    color: rgb(seed.color),
    tolerance: 24,
    sample: { mode: "single", radius: 0 },
    captured_at: "2026-06-09T00:00:00.000Z",
    note: seed.note ?? "Built-in role profile seed. Re-pick this point if UI scale changes.",
  };
}
