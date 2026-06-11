// 取色 IPC 封装 — 接入 Tauri invoke

import { invoke } from "@tauri-apps/api/core";
import { usePickerStore } from "../stores/picker";
import type { ColorRGB } from "../types/skill";

export interface CaptureAtCursorResult {
  monitor: string;
  x: number;
  y: number;
  r: number;
  g: number;
  b: number;
  hex: string;
}

export interface CaptureDiagnosticsResult {
  monitor_count: number;
  monitors: string[];
  cursor_x: number;
  cursor_y: number;
  cursor_monitor: string;
  sample: CaptureAtCursorResult | null;
  sample_error: string | null;
}

export interface CastBarRoiRequest {
  monitor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  baseline_color: ColorRGB;
  diff_threshold: number;
  min_changed_ratio: number;
  border_enabled: boolean;
  border_color: ColorRGB;
  border_tolerance: number;
  min_border_match_ratio: number;
}

export interface CastBarRoiSample {
  monitor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  pixel_count: number;
  average_color: ColorRGB;
  changed_pixel_count: number;
  changed_ratio: number;
  changed_from_baseline: boolean;
  border_pixel_count: number;
  border_match_count: number;
  border_match_ratio: number;
  border_visible: boolean;
}

export function useCapture() {
  const store = usePickerStore();

  async function samplePixel(x: number, y: number): Promise<{ r: number; g: number; b: number } | null> {
    try {
      const [r, g, b] = await invoke<[number, number, number]>("capture_sample", { x, y });
      return { r, g, b };
    } catch {
      return null;
    }
  }

  async function captureAtCursor(): Promise<CaptureAtCursorResult | null> {
    try {
      return await invoke<CaptureAtCursorResult>("capture_at_cursor");
    } catch {
      return null;
    }
  }

  async function captureDiagnostics(): Promise<CaptureDiagnosticsResult | null> {
    try {
      return await invoke<CaptureDiagnosticsResult>("capture_diagnostics");
    } catch {
      return null;
    }
  }

  async function captureCastBarRoi(request: CastBarRoiRequest): Promise<CastBarRoiSample | null> {
    try {
      return await invoke<CastBarRoiSample>("capture_cast_bar_roi", { request });
    } catch {
      return null;
    }
  }

  return { samplePixel, captureAtCursor, captureDiagnostics, captureCastBarRoi, store };
}
