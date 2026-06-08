import type { Skill } from "../types/skill";

export interface SkillDraftValidationContext {
  existingSkills: Skill[];
  editingIndex: number;
}

export function validateSkillDraft(
  skill: Skill,
  context: SkillDraftValidationContext
): string | null {
  const skillId = skill.id.trim();
  if (!skillId) return "技能 ID 不能为空";
  if (!skill.name.trim()) return "技能名称不能为空";

  const duplicateIndex = context.existingSkills.findIndex(
    (item, index) => index !== context.editingIndex && item.id.trim() === skillId
  );
  if (duplicateIndex >= 0) return `技能 ID 重复：${skillId}`;

  if (skill.enabled && !skill.trigger_key.trim()) {
    return `启用技能必须配置触发键：${skill.name.trim() || skillId}`;
  }

  const ammoCharges = new Set<number>();
  for (const stage of skill.ammo_stages) {
    if (ammoCharges.has(stage.charges_left)) {
      return `弹药阶段剩余层数重复：${stage.charges_left}`;
    }
    ammoCharges.add(stage.charges_left);
  }

  return null;
}

export function normalizeSkillDraft(skill: Skill): Skill {
  return {
    ...skill,
    id: skill.id.trim(),
    name: skill.name.trim(),
    trigger_key: skill.trigger_key.trim(),
    pixel: {
      ...skill.pixel,
      monitor: skill.pixel.monitor.trim() || "primary",
    },
    ammo_stages: skill.ammo_stages.map((stage) => ({
      ...stage,
      pixel: {
        ...stage.pixel,
        monitor: stage.pixel.monitor.trim() || "primary",
      },
    })),
  };
}
