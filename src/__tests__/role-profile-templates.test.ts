import { describe, expect, it } from "vitest";
import roleProfileSeedData from "../assets/json/role-profile-seeds.json";
import {
  buildRoleProfileTemplate,
  roleProfileTemplateOptions,
} from "../utils/role-profile-templates";
import { validateProfileForSave } from "../utils/profile-validation";

describe("role profile templates", () => {
  it("derives built-in role options from the seed asset", () => {
    expect(roleProfileTemplateOptions.map((option) => option.id)).toEqual(
      roleProfileSeedData.profiles.map((profile) => profile.id),
    );
  });

  it("builds complete save-valid profiles for built-in roles", () => {
    for (const option of roleProfileTemplateOptions) {
      const profile = buildRoleProfileTemplate(option.id);

      expect(validateProfileForSave(profile)).toEqual([]);
      expect(profile.skills.skills.length).toBeGreaterThan(0);
      expect(profile.rotations.length).toBe(1);
    }
  });

  it("includes firebrand watcher point and skill references in the same profile", () => {
    const profile = buildRoleProfileTemplate("condi_quickness_firebrand");
    const skillIds = new Set(profile.skills.skills.map((skill) => skill.id));
    const pointIds = new Set(profile.points.points.map((point) => point.id));
    const observerActions = profile.rotations[0].observer_lanes?.[0]?.actions ?? [];

    expect(skillIds.has("fb_ty2_assist")).toBe(true);
    expect(skillIds.has("fb_ty3_assist")).toBe(true);
    expect(pointIds.has("fb_point3_watch")).toBe(true);
    expect(pointIds.has("fb_point4_watch")).toBe(true);
    expect(observerActions.map((action) => action.id)).toEqual([
      "watch_ty2_visible",
      "watch_ty3_visible",
      "watch_point3_match",
      "watch_point4_match",
    ]);
  });

  it("includes the frame-driven condition weaver role with semantic skill and point references", () => {
    const profile = buildRoleProfileTemplate("condition_weaver_pistol_dagger");
    const skillIds = new Set(profile.skills.skills.map((skill) => skill.id));
    const pointIds = new Set(profile.points.points.map((point) => point.id));
    const rotation = profile.rotations[0];

    expect(skillIds.has("weaver_weave_self")).toBe(true);
    expect(skillIds.has("weaver_air_auto_1")).toBe(true);
    expect(skillIds.has("weaver_earth_auto_1")).toBe(true);
    expect(skillIds.has("weaver_air_pistol_2")).toBe(true);
    expect(skillIds.has("weaver_water_pistol_2")).toBe(true);
    expect(skillIds.has("weaver_air_dagger_4_ride_lightning")).toBe(true);
    expect(skillIds.has("weaver_fire_pistol_2")).toBe(true);
    expect(skillIds.has("weaver_earth_dagger_5_churning_earth")).toBe(true);
    expect(skillIds.has("weaver_attune_fire")).toBe(true);
    expect(pointIds.has("attune_fire_primary")).toBe(true);
    expect(pointIds.has("attune_earth_secondary")).toBe(true);
    expect(rotation.phases.map((phase) => phase.name)).toContain("Weave Self - Earth opener");
    expect(rotation.observer_lanes?.map((lane) => lane.id)).toEqual(["weaver_attunement_watchers"]);
    expect(rotation.assist_lanes?.map((lane) => lane.id)).toEqual([
      "weaver_priority_skills",
      "weaver_dagger_priority",
      "weaver_auto_attack_fill",
    ]);
  });

  it("uses sampled weaver screenshot coordinates for attunement state and cast-bar ROI", () => {
    const profile = buildRoleProfileTemplate("condition_weaver_pistol_dagger");
    const skills = new Map(profile.skills.skills.map((skill) => [skill.id, skill]));
    const points = new Map(profile.points.points.map((point) => [point.id, point]));

    expect(skills.get("weaver_attune_fire")?.trigger_key).toBe("Q");
    expect(skills.get("weaver_attune_water")?.trigger_key).toBe("E");
    expect(skills.get("weaver_attune_air")?.trigger_key).toBe("R");
    expect(skills.get("weaver_attune_earth")?.trigger_key).toBe("T");
    expect(skills.get("weaver_attune_earth")?.shots_per_cycle).toBe(0);
    expect(skills.get("weaver_auto_1")?.name).toBe("Scorching Shot");
    expect(skills.get("weaver_earth_auto_1")?.name).toBe("Piercing Pebble");
    expect(skills.get("weaver_fire_pistol_2")?.name).toBe("Raging Ricochet");
    expect(skills.get("weaver_fire_pistol_2")?.shots_per_cycle).toBe(0);
    expect(skills.get("weaver_air_pistol_2")?.trigger_key).toBe("2");
    expect(skills.get("weaver_air_dagger_4_ride_lightning")?.trigger_key).toBe("4");
    expect(points.get("attune_fire_primary")?.vx).toBe(650);
    expect(points.get("attune_fire_primary")?.vy).toBe(972);
    expect(points.get("attune_earth_secondary")?.vx).toBe(800);
    expect(points.get("attune_earth_secondary")?.vy).toBe(972);
    expect(profile.base.cast_bar.mode).toBe("roi");
    expect(profile.base.cast_bar.roi.enabled).toBe(true);
    expect(profile.base.cast_bar.roi.x).toBe(850);
    expect(profile.base.cast_bar.roi.y).toBe(815);
    expect(profile.base.cast_bar.roi.width).toBe(219);
    expect(profile.base.cast_bar.roi.height).toBe(19);
  });
});
