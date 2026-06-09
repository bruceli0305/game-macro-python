import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useEngineStore } from "../stores/engine";
import type { EngineRuntimeSnapshot } from "../types/engine";

describe("engine store runtime snapshot", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("applies runtime metrics and exposes sorted skill rows", () => {
    const store = useEngineStore();
    const snapshot: EngineRuntimeSnapshot = {
      running: true,
      paused: false,
      presetId: "default",
      stopReason: "",
      totalExecuted: 3,
      cycleCount: 2,
      phaseIndex: 1,
      phaseName: "Burst",
      uptimeMs: 1200,
      castBarRoi: {
        enabled: true,
        sampleCount: 5,
        cacheHitCount: 3,
        failedSampleCount: 1,
        lastLatencyUs: 1400,
        avgLatencyUs: 1000,
        maxLatencyUs: 1800,
        lastChangedRatio: 0.25,
        lastBorderMatchRatio: 0.5,
        lastChangedFromBaseline: true,
        lastBorderVisible: false,
        lastGone: false,
        lastError: "",
      },
      skills: [
        {
          skillId: "skill-b",
          skillName: "B Skill",
          state: "FAILED",
          nodeExec: 4,
          readyFalse: 1,
          skippedDisabled: 0,
          skippedLockBusy: 0,
          attemptStarted: 2,
          keySentOk: 1,
          castStarted: 1,
          success: 1,
          fail: 1,
          lastAttemptMs: 1200,
        },
        {
          skillId: "skill-a",
          skillName: "A Skill",
          state: "SUCCESS",
          nodeExec: 3,
          readyFalse: 0,
          skippedDisabled: 0,
          skippedLockBusy: 0,
          attemptStarted: 1,
          keySentOk: 1,
          castStarted: 1,
          success: 1,
          fail: 0,
          lastAttemptMs: 1200,
        },
      ],
    };

    store.applyRuntimeSnapshot(snapshot);

    expect(store.isRunning).toBe(true);
    expect(store.currentPhase).toBe(1);
    expect(store.cycleCount).toBe(2);
    expect(store.totalExecuted).toBe(3);
    expect(store.castBarRoi?.sampleCount).toBe(5);
    expect(store.castBarRoi?.cacheHitCount).toBe(3);
    expect(store.skillRows.map((skill) => skill.skillId)).toEqual(["skill-a", "skill-b"]);
    expect(store.skills.get("skill-b")?.fail).toBe(1);
  });
});
