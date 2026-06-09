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
});
