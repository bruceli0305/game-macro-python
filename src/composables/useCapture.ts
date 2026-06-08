// 取色 IPC 封装 — 接入 Tauri invoke

import { invoke } from "@tauri-apps/api/core";
import { usePickerStore } from "../stores/picker";

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

export function useCapture() {
  const store = usePickerStore();

  async function samplePixel(x: number, y: number): Promise<{ r: number; g: number; b: number } | null> {
    try {
      const [r, g, b] = await invoke<[number, number, number]>("capture_sample", { x, y });
      return { r, g, b };
    } catch (e) {
      console.error("capture_sample failed:", e);
      return null;
    }
  }

  async function captureAtCursor(): Promise<CaptureAtCursorResult | null> {
    try {
      return await invoke<CaptureAtCursorResult>("capture_at_cursor");
    } catch (e) {
      console.error("capture_at_cursor failed:", e);
      return null;
    }
  }

  async function captureDiagnostics(): Promise<CaptureDiagnosticsResult | null> {
    try {
      return await invoke<CaptureDiagnosticsResult>("capture_diagnostics");
    } catch (e) {
      console.error("capture_diagnostics failed:", e);
      return null;
    }
  }

  return { samplePixel, captureAtCursor, captureDiagnostics, store };
}
