import { describe, expect, it } from "vitest";
import { normalizeSkillDraft, validateSkillDraft } from "../utils/skill-validation";
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

describe("skill draft validation", () => {
  it("rejects enabled skills without trigger keys", () => {
    expect(
      validateSkillDraft(skill("sk1", ""), { existingSkills: [], editingIndex: -1 })
    ).toBe("启用技能必须配置触发键：sk1");
  });

  it("rejects duplicate skill ids", () => {
    expect(
      validateSkillDraft(skill("sk1"), {
        existingSkills: [skill("sk1")],
        editingIndex: -1,
      })
    ).toBe("技能 ID 重复：sk1");
  });

  it("rejects duplicate ammo charge stages", () => {
    const draft = skill("sk1");
    draft.ammo_stages = [
      { charges_left: 1, pixel: draft.pixel },
      { charges_left: 1, pixel: draft.pixel },
    ];

    expect(validateSkillDraft(draft, { existingSkills: [], editingIndex: -1 })).toBe(
      "弹药阶段剩余层数重复：1"
    );
  });

  it("normalizes text fields and monitor defaults", () => {
    const draft = skill(" sk1 ");
    draft.name = " Skill 1 ";
    draft.trigger_key = " 2 ";
    draft.pixel.monitor = " ";

    expect(normalizeSkillDraft(draft)).toMatchObject({
      id: "sk1",
      name: "Skill 1",
      trigger_key: "2",
      pixel: { monitor: "primary" },
    });
  });
});
