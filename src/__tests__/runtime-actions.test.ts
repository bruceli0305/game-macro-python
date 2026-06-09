import { describe, expect, it } from "vitest";
import {
  createDefaultRuntimeAction,
  markerValueOptions,
  runtimeActionTitle,
} from "../utils/runtime-actions";

const markers = [
  { id: "weapon", name: "Weapon", allowed_values: ["main", "alt"] },
  { id: "f1_state", name: "F1", allowed_values: [] },
];
const timers = [{ id: "burst", name: "Burst" }];
const counters = [{ id: "main_wp2_count", name: "Main WP2 Count" }];

describe("runtime actions utilities", () => {
  it("creates marker actions from the first declared marker", () => {
    expect(createDefaultRuntimeAction("set_marker", markers, timers, counters)).toEqual({
      type: "set_marker",
      marker_id: "weapon",
      value: "main",
    });
    expect(createDefaultRuntimeAction("clear_marker", markers, timers, counters)).toEqual({
      type: "clear_marker",
      marker_id: "weapon",
    });
  });

  it("creates timer actions from the first declared timer", () => {
    expect(createDefaultRuntimeAction("record_timer", markers, timers, counters)).toEqual({
      type: "record_timer",
      timer_id: "burst",
    });
    expect(createDefaultRuntimeAction("reset_timer", markers, timers, counters)).toEqual({
      type: "reset_timer",
      timer_id: "burst",
    });
  });

  it("creates counter actions from the first declared counter", () => {
    expect(createDefaultRuntimeAction("increment_counter", markers, timers, counters)).toEqual({
      type: "increment_counter",
      counter_id: "main_wp2_count",
      by: 1,
    });
    expect(createDefaultRuntimeAction("set_counter", markers, timers, counters)).toEqual({
      type: "set_counter",
      counter_id: "main_wp2_count",
      value: 0,
    });
    expect(createDefaultRuntimeAction("reset_counter", markers, timers, counters)).toEqual({
      type: "reset_counter",
      counter_id: "main_wp2_count",
    });
  });

  it("returns marker value options and action titles", () => {
    expect(markerValueOptions(markers, "weapon")).toEqual(["main", "alt"]);
    expect(markerValueOptions(markers, "missing")).toEqual([]);
    expect(runtimeActionTitle("reset_timer")).toBe("重置时间");
    expect(runtimeActionTitle("increment_counter")).toBe("增加计数");
  });
});
