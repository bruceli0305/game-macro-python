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
                protected_release: "yes" as any,
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

  it("accepts nearest point classifier references before save", () => {
    const profile = createDefaultProfile();
    profile.skills.skills = [skill("sk1")];
    profile.points.points = [point("fire"), point("water"), point("air"), point("earth")];
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
                condition_expr: {
                  type: "pixel_point_nearest",
                  expected_point_id: "fire",
                  candidate_point_ids: ["fire", "water", "air", "earth"],
                  max_delta: 96,
                  min_margin: 20,
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

    expect(validateProfileForSave(profile)).toEqual([]);
  });

  it("rejects invalid skill slot roles before save", () => {
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
                slot_role: "burst" as any,
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

    expect(validateProfileForSave(profile).map((item) => item.path)).toContain(
      "rotations[0].phases[0].skills[0].slot_role"
    );
  });

  it("validates assist lane config before save", () => {
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
            skills: [],
          },
        ],
        assist_lanes: [
          {
            id: "assist",
            name: "Assist",
            enabled: true,
            check_interval_ms: 5,
            interrupt_policy: "idle_only",
            skills: [
              {
                skill_id: "missing",
                priority: 1,
                label: "",
                condition_expr: null,
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                protected_release: "yes" as any,
              },
            ],
          },
          {
            id: "assist",
            name: "",
            enabled: true,
            check_interval_ms: 250,
            interrupt_policy: "bad_policy" as any,
            skills: [],
          },
        ],
      },
    ];

    const issues = validateProfileForSave(profile);
    expect(issues.map((item) => item.path)).toEqual(
      expect.arrayContaining([
        "rotations[0].assist_lanes[0].check_interval_ms",
        "rotations[0].assist_lanes[0].skills[0].skill_id",
        "rotations[0].assist_lanes[0].skills[0].protected_release",
        "rotations[0].assist_lanes[1].id",
        "rotations[0].assist_lanes[1].name",
        "rotations[0].assist_lanes[1].interrupt_policy",
      ])
    );
  });

  it("validates observer lane config before save", () => {
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
            skills: [],
          },
        ],
        state_schema: {
          markers: [],
          timers: [{ id: "cast_seen", name: "Cast seen", reset_on_cycle_start: true }],
          counters: [],
        },
        observer_lanes: [
          {
            id: "observer",
            name: "Observer",
            enabled: true,
            check_interval_ms: 5,
            actions: [
              {
                id: "",
                label: "",
                priority: 1,
                condition_expr: { type: "pixel_point", point_id: "missing", tolerance: 10 },
                actions: [],
              },
            ],
          },
          {
            id: "observer",
            name: "",
            enabled: true,
            check_interval_ms: 250,
            actions: [
              {
                id: "record_cast",
                label: "Record cast",
                priority: 1,
                condition_expr: null,
                actions: [{ type: "record_timer", timer_id: "missing_timer" }],
              },
            ],
          },
        ],
      },
    ];

    const issues = validateProfileForSave(profile);
    expect(issues.map((item) => item.path)).toEqual(
      expect.arrayContaining([
        "rotations[0].observer_lanes[0].check_interval_ms",
        "rotations[0].observer_lanes[0].actions[0].id",
        "rotations[0].observer_lanes[0].actions[0].label",
        "rotations[0].observer_lanes[0].actions[0].condition_expr",
        "rotations[0].observer_lanes[0].actions[0].actions",
        "rotations[0].observer_lanes[1].id",
        "rotations[0].observer_lanes[1].name",
        "rotations[0].observer_lanes[1].actions[0].actions[0].timer_id",
      ])
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

  it("rejects invalid slot attempt policies before save", () => {
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
                attempt_policy: {
                  max_attempts: 0,
                  start_timeout_ms: 0,
                  complete_timeout_ms: 0,
                  retry_delay_ms: 0,
                  failure_policy: "next_slot",
                  complete_fallback: "assume_success_after_timeout",
                },
              },
            ],
          },
        ],
      },
    ];

    const paths = validateProfileForSave(profile).map((item) => item.path);
    expect(paths).toContain("rotations[0].phases[0].skills[0].attempt_policy.max_attempts");
    expect(paths).toContain("rotations[0].phases[0].skills[0].attempt_policy.start_timeout_ms");
  });

  it("validates timer references before save", () => {
    const missing = createDefaultProfile();
    missing.skills.skills = [skill("sk1")];
    missing.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: { markers: [], timers: [], counters: [] },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "timer_elapsed_ge", timer_id: "missing", ms: 1000 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "record_timer", timer_id: "missing" }],
              },
            ],
          },
        ],
      },
    ];
    const missingPaths = validateProfileForSave(missing).map((item) => item.path);
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].condition_expr");
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].post_actions[0].timer_id");

    const declared = createDefaultProfile();
    declared.skills.skills = [skill("sk1")];
    declared.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: {
          markers: [],
          timers: [{ id: "burst", name: "Burst", reset_on_cycle_start: false }],
          counters: [],
        },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            entry_actions: [{ type: "record_timer", timer_id: "burst" }],
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "timer_elapsed_ge", timer_id: "burst", ms: 1000 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "reset_timer", timer_id: "burst" }],
              },
            ],
          },
        ],
      },
    ];
    expect(validateProfileForSave(declared)).toEqual([]);
  });

  it("validates marker references before save", () => {
    const missing = createDefaultProfile();
    missing.skills.skills = [skill("sk1")];
    missing.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: { markers: [], timers: [], counters: [] },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "marker_eq", marker_id: "missing", value: "main" },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "set_marker", marker_id: "missing", value: "alt" }],
              },
            ],
          },
        ],
      },
    ];
    const missingPaths = validateProfileForSave(missing).map((item) => item.path);
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].condition_expr");
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].post_actions[0].marker_id");

    const declared = createDefaultProfile();
    declared.skills.skills = [skill("sk1")];
    declared.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: {
          markers: [
            {
              id: "weapon",
              name: "Weapon",
              initial_value: "main",
              allowed_values: ["main", "alt"],
            },
          ],
          timers: [],
          counters: [],
        },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            entry_actions: [{ type: "set_marker", marker_id: "weapon", value: "main" }],
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "marker_eq", marker_id: "weapon", value: "main" },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "set_marker", marker_id: "weapon", value: "alt" }],
              },
            ],
          },
        ],
      },
    ];
    expect(validateProfileForSave(declared)).toEqual([]);
  });

  it("validates counter references before save", () => {
    const missing = createDefaultProfile();
    missing.skills.skills = [skill("sk1")];
    missing.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: { markers: [], timers: [], counters: [] },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "counter_ge", counter_id: "missing", value: 1 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "increment_counter", counter_id: "missing", by: 1 }],
              },
            ],
          },
        ],
      },
    ];
    const missingPaths = validateProfileForSave(missing).map((item) => item.path);
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].condition_expr");
    expect(missingPaths).toContain("rotations[0].phases[0].skills[0].post_actions[0].counter_id");

    const declared = createDefaultProfile();
    declared.skills.skills = [skill("sk1")];
    declared.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: {
          markers: [],
          timers: [],
          counters: [
            {
              id: "main_wp2_count",
              name: "Main WP2 Count",
              initial_value: 0,
              reset_on_phase_entry: false,
              reset_on_cycle_start: true,
            },
          ],
        },
        phases: [
          {
            name: "phase",
            complete_when: "any_fired",
            entry_actions: [{ type: "reset_counter", counter_id: "main_wp2_count" }],
            skills: [
              {
                skill_id: "sk1",
                priority: 1,
                label: "",
                condition_expr: { type: "counter_ge", counter_id: "main_wp2_count", value: 1 },
                start_expr: null,
                complete_expr: null,
                override_cast_ms: null,
                post_actions: [{ type: "increment_counter", counter_id: "main_wp2_count", by: 1 }],
              },
            ],
          },
        ],
      },
    ];
    expect(validateProfileForSave(declared)).toEqual([]);
  });

  it("validates phase transition targets before save", () => {
    const missing = createDefaultProfile();
    missing.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        phases: [
          {
            name: "P1",
            complete_when: "any_fired",
            transition_rules: [
              {
                label: "missing",
                condition_expr: { type: "const", value: true },
                target_phase: "Missing",
              },
            ],
            fallback_transition: { type: "phase", target_phase: "Missing" },
            skills: [],
          },
        ],
      },
    ];
    const missingPaths = validateProfileForSave(missing).map((item) => item.path);
    expect(missingPaths).toContain("rotations[0].phases[0].transition_rules[0].target_phase");
    expect(missingPaths).toContain("rotations[0].phases[0].fallback_transition.target_phase");

    const declared = createDefaultProfile();
    declared.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 100,
        max_cycles: 0,
        phases: [
          {
            name: "P1",
            complete_when: "any_fired",
            transition_rules: [
              {
                label: "to-p2",
                condition_expr: { type: "const", value: true },
                target_phase: "P2",
              },
            ],
            fallback_transition: { type: "phase", target_phase: "P2" },
            skills: [],
          },
          {
            name: "P2",
            complete_when: "any_fired",
            skills: [],
          },
        ],
      },
    ];
    expect(validateProfileForSave(declared)).toEqual([]);
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
    expect(validateProfileForSave(profile).map((item) => item.path)).toContain("base.cast_bar.mode");
  });

  it("accepts cast bar ROI mode without a point reference", () => {
    const profile = createDefaultProfile();
    profile.base.cast_bar.mode = "roi";
    profile.base.cast_bar.point_id = "";
    profile.base.cast_bar.roi.enabled = true;
    profile.base.cast_bar.roi.monitor = "primary";
    profile.base.cast_bar.roi.width = 320;
    profile.base.cast_bar.roi.height = 28;

    expect(validateProfileForSave(profile).map((item) => item.path)).not.toContain(
      "base.cast_bar.point_id"
    );
  });

  it("rejects enabled cast bar ROI without dimensions", () => {
    const profile = createDefaultProfile();
    profile.base.cast_bar.roi.enabled = true;
    profile.base.cast_bar.roi.width = 0;
    profile.base.cast_bar.roi.height = 0;

    expect(validateProfileForSave(profile).map((item) => item.path)).toEqual(
      expect.arrayContaining(["base.cast_bar.roi.width", "base.cast_bar.roi.height"])
    );
  });

  it("rejects invalid rotation poll intervals before save", () => {
    const profile = createDefaultProfile();
    profile.rotations = [
      {
        name: "cycle",
        poll_interval_ms: 0,
        max_cycles: 0,
        phases: [],
      },
    ];
    expect(validateProfileForSave(profile).map((item) => item.path)).toContain(
      "rotations[0].poll_interval_ms"
    );
  });
});
