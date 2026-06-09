import { describe, expect, it } from "vitest";
import { buildCyclePreset, cyclePresetOptions } from "../utils/cycle-presets";

describe("cycle presets", () => {
  it("exposes the two AHK-derived templates", () => {
    expect(cyclePresetOptions.map((option) => option.value)).toEqual([
      "power_virtuoso_greatsword",
      "condi_quickness_firebrand",
    ]);
  });

  it("builds the power virtuoso state-machine phase layout", () => {
    const preset = buildCyclePreset("power_virtuoso_greatsword");

    expect(preset.phases.map((phase) => phase.name)).toEqual([
      "入口判定",
      "副武器起手",
      "主武器循环",
      "副武器循环",
      "主武器起手修正",
      "切武器爆发",
    ]);
    expect(preset.state_schema?.markers.some((marker) => marker.id === "weapon")).toBe(true);
    expect(preset.state_schema?.counters.some((counter) => counter.id === "main_wp4_count")).toBe(true);
    expect(preset.phases.flatMap((phase) => phase.skills).some((skill) => skill.protected_release)).toBe(true);
    expect(preset.assist_lanes).toEqual([]);
  });

  it("builds the firebrand template with assist lane and protected release guards", () => {
    const preset = buildCyclePreset("condi_quickness_firebrand");
    const assistLane = preset.assist_lanes?.[0];

    expect(preset.phases.map((phase) => phase.name)).toContain("F1 打开处理");
    expect(assistLane?.interrupt_policy).toBe("complete_wait");
    expect(assistLane?.skills.map((skill) => skill.skill_id)).toEqual([
      "fb_ty2_assist",
      "fb_ty3_assist",
      "fb_ty1_assist",
    ]);
    expect(assistLane?.skills.every((skill) => skill.post_actions?.[0]?.type === "record_timer")).toBe(true);
    expect(preset.phases.flatMap((phase) => phase.skills).some((skill) => skill.protected_release)).toBe(true);
  });
});
