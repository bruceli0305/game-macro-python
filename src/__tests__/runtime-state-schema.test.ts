import { describe, expect, it } from "vitest";
import {
  createDefaultRuntimeCounter,
  createDefaultRuntimeMarker,
  createDefaultRuntimeTimer,
  nextRuntimeStateId,
  parseAllowedMarkerValues,
} from "../utils/runtime-state-schema";

describe("runtime state schema utilities", () => {
  it("generates stable unique ids", () => {
    expect(nextRuntimeStateId("marker", ["marker_1", "marker_2"])).toBe("marker_3");
    expect(nextRuntimeStateId("timer", ["timer_1", "timer_3"])).toBe("timer_2");
    expect(nextRuntimeStateId("counter", ["counter_1", "counter_3"])).toBe("counter_2");
  });

  it("normalizes marker allowed values", () => {
    expect(parseAllowedMarkerValues("main, alt，open\nalt")).toEqual(["main", "alt", "open"]);
  });

  it("creates default runtime state declarations", () => {
    expect(createDefaultRuntimeMarker(["marker_1"], 1)).toMatchObject({
      id: "marker_2",
      name: "运行标记 2",
      initial_value: "",
      allowed_values: [],
    });
    expect(createDefaultRuntimeTimer(["timer_1"], 1)).toMatchObject({
      id: "timer_2",
      name: "时间标记 2",
      reset_on_cycle_start: true,
    });
    expect(createDefaultRuntimeCounter(["counter_1"], 1)).toMatchObject({
      id: "counter_2",
      name: "计数器 2",
      initial_value: 0,
      reset_on_phase_entry: false,
      reset_on_cycle_start: true,
    });
  });
});
