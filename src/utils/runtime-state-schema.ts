import type { RuntimeCounterDef, RuntimeMarkerDef, RuntimeTimerDef } from "../types/cycle";

export function nextRuntimeStateId(prefix: string, ids: Iterable<string>): string {
  const existing = new Set(ids);
  let index = 1;
  let candidate = `${prefix}_${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `${prefix}_${index}`;
  }
  return candidate;
}

export function parseAllowedMarkerValues(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

export function createDefaultRuntimeMarker(existingIds: Iterable<string>, index: number): RuntimeMarkerDef {
  return {
    id: nextRuntimeStateId("marker", existingIds),
    name: `运行标记 ${index + 1}`,
    initial_value: "",
    allowed_values: [],
  };
}

export function createDefaultRuntimeTimer(existingIds: Iterable<string>, index: number): RuntimeTimerDef {
  return {
    id: nextRuntimeStateId("timer", existingIds),
    name: `时间标记 ${index + 1}`,
    reset_on_cycle_start: true,
  };
}

export function createDefaultRuntimeCounter(
  existingIds: Iterable<string>,
  index: number
): RuntimeCounterDef {
  return {
    id: nextRuntimeStateId("counter", existingIds),
    name: `计数器 ${index + 1}`,
    initial_value: 0,
    reset_on_phase_entry: false,
    reset_on_cycle_start: true,
  };
}
