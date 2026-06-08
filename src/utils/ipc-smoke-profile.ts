import { createDefaultProfile } from "../composables/useProfile";
import type { Profile } from "../types/profile";

export function createIpcSmokeProfile(name = "ipc-smoke"): Profile {
  const profile = createDefaultProfile(name);

  profile.points.points = [
    {
      id: "smoke-point",
      name: "IPC 自检点位",
      monitor: "primary",
      vx: 10,
      vy: 20,
      color: { r: 12, g: 34, b: 56 },
      tolerance: 0,
      sample: { mode: "single", radius: 0 },
      captured_at: new Date().toISOString(),
      note: "IPC smoke fixture",
    },
  ];

  profile.skills.skills = [
    {
      id: "smoke-skill",
      name: "IPC 自检技能",
      enabled: true,
      trigger_key: "1",
      cast: { readbar_ms: 0, cooldown_ms: 0 },
      pixel: {
        monitor: "primary",
        vx: 30,
        vy: 40,
        color: { r: 90, g: 120, b: 150 },
        tolerance: 0,
        sample: { mode: "single", radius: 0 },
      },
      note: "IPC smoke fixture",
      game_id: 0,
      game_desc: "",
      icon_url: "",
      cooldown_ms: 0,
      radius: 0,
      shots_per_cycle: 1,
      ammo_stages: [],
    },
  ];

  profile.rotations = [
    {
      name: "IPC 自检循环",
      poll_interval_ms: 10,
      max_cycles: 1,
      phases: [
        {
          name: "P1",
          complete_when: "any_fired",
          skills: [
            {
              skill_id: "smoke-skill",
              priority: 1,
              label: "smoke-skill",
              condition_expr: {
                type: "pixel_point",
                point_id: "smoke-point",
                tolerance: 0,
              },
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
