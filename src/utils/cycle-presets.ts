import cyclePresetData from "../assets/json/cycle-presets.json";
import type { CycleConfig } from "../types/cycle";

export type CyclePresetId =
  | "power_virtuoso_greatsword"
  | "condi_quickness_firebrand"
  | "condition_weaver_pistol_dagger";

export interface CyclePresetOption {
  label: string;
  value: CyclePresetId;
  description: string;
}

interface CyclePresetDefinition extends CyclePresetOption {
  rotation: CycleConfig;
}

interface CyclePresetFile {
  schema_version: number;
  presets: CyclePresetDefinition[];
}

const presetFile = cyclePresetData as unknown as CyclePresetFile;
const presetsById = new Map<CyclePresetId, CyclePresetDefinition>(
  presetFile.presets.map((preset) => [preset.value, preset]),
);

export const cyclePresetOptions: CyclePresetOption[] = presetFile.presets.map(
  ({ label, value, description }) => ({ label, value, description }),
);

export function buildCyclePreset(id: CyclePresetId): CycleConfig {
  const preset = presetById(id);
  return JSON.parse(JSON.stringify(preset.rotation)) as CycleConfig;
}

export function getCyclePresetLabel(id: CyclePresetId): string {
  return presetById(id).label;
}

function presetById(id: CyclePresetId): CyclePresetDefinition {
  const preset = presetsById.get(id);
  if (!preset) {
    throw new Error(`Missing built-in cycle preset: ${id}`);
  }
  return preset;
}
