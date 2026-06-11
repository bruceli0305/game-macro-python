import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  appendDebugRunEventForTest,
  clearDebugRunState,
  finishDebugRunForTest,
  startDebugRunForTest,
  useDebugRun,
} from "../composables/useDebugRun";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(),
}));

describe("useDebugRun", () => {
  beforeEach(() => {
    clearDebugRunState();
  });

  it("tracks started, event, and completed states", () => {
    const debugRun = useDebugRun();

    startDebugRunForTest({
      run_id: "run-1",
      start_phase_index: 0,
      end_phase_index: 1,
      started_at_ms: 0,
    });
    appendDebugRunEventForTest({
      run_id: "run-1",
      ts_ms: 10,
      phase_index: 0,
      phase_name: "P1",
      skill_id: "skill-1",
      skill_name: "Skill 1",
      key: "1",
      event: "execute",
      outcome: "SUCCESS",
      reason: "assume_success",
    });
    finishDebugRunForTest({
      run_id: "run-1",
      status: "completed",
      reason: "range_completed",
      elapsed_ms: 10,
      total_events: 1,
    });

    expect(debugRun.status.value).toBe("completed");
    expect(debugRun.logs.value).toHaveLength(1);
    expect(debugRun.logs.value[0].key).toBe("1");
    expect(debugRun.elapsedMs.value).toBe(10);
    expect(debugRun.latestError.value).toBe("");
  });

  it("ignores stale events from older runs", () => {
    const debugRun = useDebugRun();

    startDebugRunForTest({
      run_id: "run-2",
      start_phase_index: 0,
      end_phase_index: 0,
      started_at_ms: 0,
    });
    appendDebugRunEventForTest({
      run_id: "run-1",
      ts_ms: 10,
      phase_index: 0,
      phase_name: "P1",
      skill_id: "skill-1",
      skill_name: "Skill 1",
      key: "1",
      event: "execute",
      outcome: "SUCCESS",
      reason: "stale",
    });

    expect(debugRun.status.value).toBe("running");
    expect(debugRun.logs.value).toHaveLength(0);
  });
});
