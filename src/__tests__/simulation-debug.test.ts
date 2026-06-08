import { describe, expect, it } from "vitest";
import { simulationDebugJson, summarizeSimulation } from "../utils/simulation-debug";

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
];

describe("simulation debug helpers", () => {
  it("summarizes simulation events", () => {
    expect(summarizeSimulation(events)).toMatchObject({
      total: 4,
      executed: 2,
      skipped: 2,
      success: 1,
      notReady: 2,
      failed: 1,
      durationMs: 400,
      uniqueSkills: 3,
      topReasons: [
        { reason: "condition_false:pixel", count: 2 },
        { reason: "send_key_failed", count: 1 },
        { reason: "success", count: 1 },
      ],
    });
  });

  it("exports debug JSON with summary and events", () => {
    const parsed = JSON.parse(simulationDebugJson(events));

    expect(parsed.summary.total).toBe(4);
    expect(parsed.events).toHaveLength(4);
    expect(typeof parsed.generatedAt).toBe("string");
  });
});
