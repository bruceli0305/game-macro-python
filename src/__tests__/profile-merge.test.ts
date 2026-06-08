import { describe, expect, it } from "vitest";
import {
  createDefaultProfile,
  withProfilePoints,
  withProfileRotations,
  withProfileSkills,
} from "../composables/useProfile";
import type { CycleConfig } from "../types/cycle";
import type { Point } from "../types/point";
import type { Skill } from "../types/skill";

function makeSkill(id: string): Skill {
  return {
    id,
    name: id,
    enabled: true,
    trigger_key: "1",
    cast: { readbar_ms: 0, cooldown_ms: 0 },
    pixel: {
      monitor: "primary",
      vx: 0,
      vy: 0,
      color: { r: 255, g: 255, b: 255 },
      tolerance: 20,
      sample: { mode: "single", radius: 0 },
    },
    note: "",
    game_id: 0,
    game_desc: "",
    icon_url: "",
    cooldown_ms: 0,
    radius: 0,
    shots_per_cycle: 1,
    ammo_stages: [],
  };
}

function makePoint(id: string): Point {
  return {
    id,
    name: id,
    monitor: "primary",
    vx: 10,
    vy: 20,
    color: { r: 1, g: 2, b: 3 },
    tolerance: 20,
    sample: { mode: "single", radius: 0 },
    captured_at: "2026-06-02T00:00:00.000Z",
    note: "",
  };
}

function makeRotation(name: string): CycleConfig {
  return {
    name,
    phases: [{ name: "P1", skills: [], complete_when: "any_fired" }],
    poll_interval_ms: 100,
    max_cycles: 0,
  };
}

describe("profile section updates", () => {
  it("updates skills without dropping points or rotations", () => {
    const base = createDefaultProfile();
    const withPoints = withProfilePoints(base, [makePoint("pt1")]);
    const withRotations = withProfileRotations(withPoints, [makeRotation("cycle1")]);

    const next = withProfileSkills(withRotations, [makeSkill("sk1")]);

    expect(next.skills.skills.map((skill) => skill.id)).toEqual(["sk1"]);
    expect(next.points.points.map((point) => point.id)).toEqual(["pt1"]);
    expect(next.rotations.map((rotation) => rotation.name)).toEqual(["cycle1"]);
  });

  it("updates rotations without dropping skills or points", () => {
    const base = createDefaultProfile();
    const withSkills = withProfileSkills(base, [makeSkill("sk1")]);
    const withPoints = withProfilePoints(withSkills, [makePoint("pt1")]);

    const next = withProfileRotations(withPoints, [makeRotation("cycle2")]);

    expect(next.skills.skills.map((skill) => skill.id)).toEqual(["sk1"]);
    expect(next.points.points.map((point) => point.id)).toEqual(["pt1"]);
    expect(next.rotations.map((rotation) => rotation.name)).toEqual(["cycle2"]);
  });
});
