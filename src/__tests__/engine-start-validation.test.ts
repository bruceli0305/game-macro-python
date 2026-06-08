import { describe, expect, it } from "vitest";
import { createDefaultProfile } from "../composables/useProfile";
import { validateProfileForEngineStart, validateProfileForRun } from "../utils/profile-validation";
import type { Skill } from "../types/skill";

function skill(id: string): Skill {
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

function executableProfile() {
  const profile = createDefaultProfile();
  profile.skills.skills = [skill("sk1")];
  profile.rotations = [
    {
      name: "cycle",
      poll_interval_ms: 100,
      max_cycles: 0,
      phases: [
        {
          name: "phase",
          complete_when: "any_fired",
          skills: [
            {
              skill_id: "sk1",
              priority: 1,
              label: "",
              condition_expr: null,
              start_expr: null,
              complete_expr: null,
              override_cast_ms: null,
            },
          ],
        },
      ],
    },
  ];
  return profile;
}

describe("engine start validation", () => {
  it("allows offline run validation when execution is disabled", () => {
    const profile = executableProfile();
    profile.base.exec.enabled = false;

    expect(validateProfileForRun(profile)).toEqual([]);
  });

  it("rejects engine start when execution is disabled", () => {
    const profile = executableProfile();
    profile.base.exec.enabled = false;

    expect(validateProfileForEngineStart(profile).map((item) => item.message)).toContain(
      "请先在基础配置中启用宏执行"
    );
  });

  it("allows engine start when execution is enabled", () => {
    const profile = executableProfile();
    profile.base.exec.enabled = true;

    expect(validateProfileForEngineStart(profile)).toEqual([]);
  });
});
