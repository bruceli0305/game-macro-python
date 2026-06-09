import type { RuntimeAction } from "../types/cycle";

export interface RuntimeMarkerOption {
  id: string;
  name: string;
  allowed_values?: string[];
}

export interface RuntimeTimerOption {
  id: string;
  name: string;
}

export interface RuntimeCounterOption {
  id: string;
  name: string;
}

export type RuntimeActionType = RuntimeAction["type"];

export function markerValueOptions(
  markers: RuntimeMarkerOption[] | undefined,
  markerId: string
): string[] {
  return markers?.find((marker) => marker.id === markerId)?.allowed_values ?? [];
}

export function createDefaultRuntimeAction(
  type: RuntimeActionType,
  markers: RuntimeMarkerOption[] | undefined,
  timers: RuntimeTimerOption[] | undefined,
  counters: RuntimeCounterOption[] | undefined = []
): RuntimeAction {
  const marker = markers?.[0];
  const timer = timers?.[0];
  const counter = counters?.[0];

  switch (type) {
    case "set_marker":
      return {
        type,
        marker_id: marker?.id ?? "",
        value: marker?.allowed_values?.[0] ?? "",
      };
    case "clear_marker":
      return {
        type,
        marker_id: marker?.id ?? "",
      };
    case "record_timer":
    case "reset_timer":
      return {
        type,
        timer_id: timer?.id ?? "",
      };
    case "increment_counter":
      return {
        type,
        counter_id: counter?.id ?? "",
        by: 1,
      };
    case "set_counter":
      return {
        type,
        counter_id: counter?.id ?? "",
        value: 0,
      };
    case "reset_counter":
      return {
        type,
        counter_id: counter?.id ?? "",
      };
  }
}

export function runtimeActionTitle(type: RuntimeActionType): string {
  switch (type) {
    case "set_marker":
      return "设置标记";
    case "clear_marker":
      return "清除标记";
    case "record_timer":
      return "记录时间";
    case "reset_timer":
      return "重置时间";
    case "increment_counter":
      return "增加计数";
    case "set_counter":
      return "设置计数";
    case "reset_counter":
      return "重置计数";
  }
}
