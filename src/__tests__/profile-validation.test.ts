import { describe, expect, it } from "vitest";
import { createDefaultProfile } from "../composables/useProfile";
import { validateProfileForRun, validateProfileForSave } from "../utils/profile-validation";
import type { Point } from "../types/point";
import type { Skill } from "../types/skill";

function skill(id: string, triggerKey = "1"): Skill {
  return {
    id,
    name: id,
    enabled: true,
    trigger_key: triggerKey,
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

function point(id: string): Point {
  return {
    id,
    name: id,
    monitor: "primary",
    vx: 10,
    vy: 20,
    color: { r: 1, g: 2, b: 3 },
    tolerance: 10,
    sample: { mode: "single", radius: 0 },
    captured_at: "2026-06-08T00:00:00.000Z",
    note: "",
  };
}

describe("profile validation", () => {
  it("rejects missing slot skill references before save", () => {
    const profile = createDefaultProfile();
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
                skill_id: "missing",
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

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "技能槽引用了不存在的技能：missing"
    );
  });

  it("rejects missing point references in expressions before save", () => {
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
                condition_expr: { type: "pixel_point", point_id: "pt-missing", tolerance: 10 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
              },
            ],
          },
        ],
      },
    ];

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "引用了不存在的点位：pt-missing"
    );
  });

  it("allows a complete executable profile to run", () => {
    const profile = createDefaultProfile();
    profile.skills.skills = [skill("sk1")];
    profile.points.points = [point("pt1")];
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
                condition_expr: { type: "pixel_point", point_id: "pt1", tolerance: 10 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
              },
            ],
          },
        ],
      },
    ];

    expect(validateProfileForRun(profile)).toEqual([]);
  });

  it("rejects enabled executable skills without trigger keys before run", () => {
    const profile = createDefaultProfile();
    profile.skills.skills = [skill("sk1", "")];
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

    expect(validateProfileForRun(profile).map((item) => item.message)).toContain(
      "启用技能缺少触发键：sk1"
    );
  });

  it("rejects duplicate ammo charge stages before save", () => {
    const profile = createDefaultProfile();
    const sk = skill("sk1");
    sk.ammo_stages = [
      { charges_left: 1, pixel: sk.pixel },
      { charges_left: 1, pixel: sk.pixel },
    ];
    profile.skills.skills = [sk];

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "弹药阶段剩余层数重复：1"
    );
  });
  it("rejects invalid point sample modes before save", () => {
    const profile = createDefaultProfile();
    const pt = point("pt1");
    pt.sample.mode = "median";
    profile.points.points = [pt];

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "采样模式必须是 single 或 mean_square"
    );
  });

  it("rejects invalid skill pixel monitors before save", () => {
    const profile = createDefaultProfile();
    const sk = skill("sk1");
    sk.pixel.monitor = "";
    profile.skills.skills = [sk];

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "像素配置必须指定显示器"
    );
  });

  it("rejects invalid base execution timing before save", () => {
    const profile = createDefaultProfile();
    profile.base.exec.poll_not_ready_ms = 0;

    expect(validateProfileForSave(profile).map((item) => item.path)).toContain(
      "base.exec.poll_not_ready_ms"
    );
  });

  it("rejects invalid cast bar mode before save", () => {
    const profile = createDefaultProfile();
    profile.base.cast_bar.mode = "unknown";

    expect(validateProfileForSave(profile).map((item) => item.path)).toContain(
      "base.cast_bar.mode"
    );
  });

  it("rejects invalid rotation poll intervals before save", () => {
    const profile = createDefaultProfile();
    profile.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        phases: [],
      },
    ];
    profile.rotations[0].poll_interval_ms = 0;

    expect(validateProfileForSave(profile).map((item) => item.path)).toContain(
      "rotations[0].poll_interval_ms"
    );
  });
});
