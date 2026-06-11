import { describe, expect, it } from "vitest";
import cyclePresetData from "../assets/json/cycle-presets.json";
import { buildCyclePreset, cyclePresetOptions } from "../utils/cycle-presets";

describe("cycle presets", () => {
  it("derives preset options from the cycle preset asset", () => {
    expect(cyclePresetOptions.map((option) => option.value)).toEqual(
      cyclePresetData.presets.map((preset) => preset.value),
    );
  });

  it("exposes the built-in role cycle templates", () => {
    expect(cyclePresetOptions.map((option) => option.value)).toEqual([
      "power_virtuoso_greatsword",
      "condi_quickness_firebrand",
      "condition_weaver_pistol_dagger",
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
    const observerLane = preset.observer_lanes?.[0];

    expect(preset.phases.map((phase) => phase.name)).toContain("F1 打开处理");
    expect(observerLane?.id).toBe("firebrand_cast_watchers");
    expect(observerLane?.actions.map((action) => action.id)).toEqual([
      "watch_ty2_visible",
      "watch_ty3_visible",
      "watch_point3_match",
      "watch_point4_match",
    ]);
    expect(observerLane?.actions.every((action) => action.actions[0]?.type === "record_timer")).toBe(true);
    expect(preset.state_schema?.timers.map((timer) => timer.id)).toEqual(
      expect.arrayContaining(["ty2_seen", "ty3_seen", "point3_seen", "point4_seen"])
    );
    expect(assistLane?.interrupt_policy).toBe("complete_wait");
    expect(assistLane?.skills.map((skill) => skill.skill_id)).toEqual([
      "fb_ty2_assist",
      "fb_ty3_assist",
      "fb_ty1_assist",
    ]);
    expect(assistLane?.skills.every((skill) => skill.post_actions?.[0]?.type === "record_timer")).toBe(true);
    expect(preset.phases.flatMap((phase) => phase.skills).some((skill) => skill.protected_release)).toBe(true);
  });

  it("builds the condition weaver template with frame-confirmed semantic slots", () => {
    const preset = buildCyclePreset("condition_weaver_pistol_dagger");
    const phaseNames = preset.phases.map((phase) => phase.name);
    const serializedPreset = JSON.stringify(preset);
    const observerLane = preset.observer_lanes?.find((lane) => lane.id === "weaver_attunement_watchers");
    const priorityLane = preset.assist_lanes?.find((lane) => lane.id === "weaver_priority_skills");
    const daggerLane = preset.assist_lanes?.find((lane) => lane.id === "weaver_dagger_priority");
    const autoLane = preset.assist_lanes?.find((lane) => lane.id === "weaver_auto_attack_fill");
    const syncSlot = preset.phases[0]?.skills[0];
    const airEarthPhase = preset.phases.find((phase) => phase.name === "Weave Self - Air/Earth");
    const fireAirPhase = preset.phases.find((phase) => phase.name === "Weave Self - Fire/Air");
    const earthFinalPhase = preset.phases.find((phase) => phase.name === "Weave Self - Earth final");
    const waterEarthPhase = preset.phases.find((phase) => phase.name === "Weave Self - Water/Earth");
    const fireWaterPhase = preset.phases.find((phase) => phase.name === "Weave Self - Fire/Water");
    const loopEarthPhase = preset.phases.find((phase) => phase.name === "Loop - Earth/Earth");

    expect(preset.phases[0]?.name).toBe("Preparation - sync Earth primary");
    expect(syncSlot?.skill_id).toBe("weaver_attune_earth");
    expect(syncSlot?.condition_expr).toMatchObject({
      type: "not",
      child: {
        type: "pixel_point_nearest",
        expected_point_id: "attune_earth_primary",
      },
    });
    expect(syncSlot?.complete_expr).toMatchObject({
      type: "pixel_point_nearest",
      expected_point_id: "attune_earth_primary",
    });
    expect(phaseNames).toEqual(
      expect.arrayContaining([
        "Preparation - stock Earth bullet",
        "Weave Self - Earth opener",
        "Weave Self - Water/Earth",
        "Loop - Fire/Fire",
        "Loop - Fire/Earth",
      ]),
    );
    expect(observerLane?.actions.map((action) => action.id)).toEqual([
      "watch_fire_fire",
      "watch_earth_earth",
      "watch_air",
      "watch_water",
      "watch_fire_earth",
      "watch_earth_fire",
      "watch_air_earth",
      "watch_fire_air",
      "watch_water_earth",
      "watch_fire_water",
    ]);
    expect(priorityLane?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_signet_fire",
      "weaver_signet_earth",
      "weaver_primordial_stance",
    ]);
    expect(daggerLane?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_fire_dagger_4_ring_of_fire",
      "weaver_fire_dagger_5_fire_grab",
      "weaver_earth_dagger_4_earthquake",
      "weaver_earth_dagger_5_churning_earth",
    ]);
    expect(autoLane?.skills[0]?.skill_id).toBe("weaver_auto_1");
    expect(autoLane?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_auto_1",
      "weaver_earth_auto_1",
    ]);
    expect(autoLane?.skills.map((slot) => slot.slot_role)).toEqual(["filler", "filler"]);
    expect(airEarthPhase?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_attune_air",
      "weaver_signet_fire",
      "weaver_air_auto_1",
      "weaver_air_pistol_2",
      "weaver_air_earth_dual_3",
    ]);
    expect(fireAirPhase?.skills.map((slot) => slot.skill_id)).toContain("weaver_air_dagger_4_ride_lightning");
    expect(fireAirPhase?.skills.map((slot) => slot.skill_id)).not.toContain("weaver_fire_dagger_4_ring_of_fire");
    expect(earthFinalPhase?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_attune_earth",
      "weaver_earth_dagger_4_earthquake",
      "weaver_earth_dagger_5_churning_earth",
      "weaver_earth_dual_3",
    ]);
    expect(waterEarthPhase?.skills.map((slot) => slot.skill_id)).toContain("weaver_water_pistol_2");
    expect(waterEarthPhase?.skills.map((slot) => slot.skill_id)).not.toContain("weaver_earth_pistol_2");
    expect(fireWaterPhase?.skills.map((slot) => slot.skill_id)).toEqual([
      "weaver_attune_fire",
      "weaver_fire_water_dual_3",
      "weaver_signet_fire",
      "weaver_fire_pistol_2",
      "weaver_auto_1",
    ]);
    expect(fireWaterPhase?.skills.map((slot) => slot.slot_role)).toEqual([
      "mandatory",
      "mandatory",
      "priority",
      "mandatory",
      "filler",
    ]);
    expect(loopEarthPhase?.transition_rules?.[0]).toMatchObject({
      label: "Weave Self ready at Earth/Earth",
      target_phase: "Weave Self - Earth opener",
    });
    expect(preset.state_schema?.markers[0]?.id).toBe("attunement");
    expect(serializedPreset).toContain("attune_fire_primary");
    expect(serializedPreset).toContain("pixel_point_nearest");
    expect(serializedPreset).toContain("candidate_point_ids");
    expect(serializedPreset).toContain("min_margin");
    expect(serializedPreset).toContain("weaver_fire_pistol_2");
    expect(serializedPreset).not.toContain("weaver_weapon_2");
    expect(serializedPreset).not.toContain("weaver_weapon_3");
    expect(serializedPreset).not.toContain("weaver_weapon_4");
    expect(serializedPreset).not.toContain("weaver_weapon_5");
  });
});
