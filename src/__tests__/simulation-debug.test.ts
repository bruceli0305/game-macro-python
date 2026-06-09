import { describe, expect, it } from "vitest";
import {
  simulationDebugJson,
  simulationEventLabel,
  simulationReasonLabel,
  summarizeSimulation,
} from "../utils/simulation-debug";

const events = [
  {
    event: "attempt",
    outcome: "Success",
    reason: "success",
    timeMs: 100,
    skillId: "sk1",
  },
  {
    event: "skip",
    outcome: "NOT_READY",
    reason: "condition_false:pixel",
    timeMs: 200,
    skillId: "sk2",
  },
  {
    event: "skip",
    outcome: "NOT_READY",
    reason: "condition_false:pixel",
    timeMs: 300,
    skillId: "sk2",
  },
  {
    event: "attempt",
    outcome: "Failed",
    reason: "send_key_failed",
    timeMs: 400,
    skillId: "sk3",
  },
  {
    event: "phase_transition",
    outcome: "Applied",
    reason: "rule:burst->P3",
    timeMs: 500,
    skillId: "",
  },
  {
    event: "assist_execute",
    outcome: "Success",
    reason: "success",
    timeMs: 550,
    skillId: "assist1",
  },
  {
    event: "assist_skip",
    outcome: "NOT_READY",
    reason: "cooldown_until=700",
    timeMs: 600,
    skillId: "assist2",
  },
];

describe("simulation debug helpers", () => {
  it("summarizes simulation events", () => {
    const summary = summarizeSimulation(events);
    expect(summary).toMatchObject({
      total: 7,
      executed: 3,
      skipped: 3,
      transitions: 1,
      runtimeActions: 0,
      success: 2,
      notReady: 3,
      failed: 1,
      durationMs: 600,
      uniqueSkills: 5,
    });
    expect(summary.topReasons[0]).toEqual({ reason: "condition_false:pixel", count: 2 });
    expect(summary.topReasons).toContainEqual({ reason: "rule:burst->P3", count: 1 });
  });

  it("exports debug JSON with summary and events", () => {
    const parsed = JSON.parse(simulationDebugJson(events));

    expect(parsed.summary.total).toBe(7);
    expect(parsed.events).toHaveLength(7);
    expect(typeof parsed.generatedAt).toBe("string");
  });

  it("labels phase transition events and reasons", () => {
    expect(simulationEventLabel("phase_transition")).toBe("阶段跳转");
    expect(simulationEventLabel("assist_execute")).toBe("辅助执行");
    expect(simulationEventLabel("assist_skip")).toBe("辅助跳过");
    expect(simulationReasonLabel("rule:burst->P3")).toBe("命中跳转规则（rule:burst->P3）");
  });
});
