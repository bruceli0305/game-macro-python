import { describe, expect, it, vi } from "vitest";
import { createDefaultProfile } from "../composables/useProfile";
import { ipcSmokeDebugJson, runDesktopIpcSmoke } from "../utils/desktop-ipc-smoke";
import { createIpcSmokeProfile } from "../utils/ipc-smoke-profile";
import type { Profile } from "../types/profile";
import type { Skill } from "../types/skill";
import type { EnginePreflightReport } from "../composables/useEngine";
import type { CaptureDiagnosticsResult } from "../composables/useCapture";
import type { HotkeyDiagnosticsResult } from "../composables/useHotkeys";

function skill(id: string): Skill {
  return {
    id,
    name: id,
    enabled: true,
    trigger_key: "1",
    cast: { readbar_ms: 0, cooldown_ms: 0 },
    pixel: {
      monitor: "primary",
      vx: 0,
      vy: 0,
      color: { r: 255, g: 255, b: 255 },
      tolerance: 20,
      sample: { mode: "single", radius: 0 },
    },
    note: "",
    game_id: 0,
    game_desc: "",
    icon_url: "",
    cooldown_ms: 0,
    radius: 0,
    shots_per_cycle: 1,
    ammo_stages: [],
  };
}

function executableProfile(): Profile {
  const profile = createDefaultProfile();
  profile.skills.skills = [skill("sk1")];
  profile.rotations = [
    {
      name: "cycle",
      poll_interval_ms: 100,
      max_cycles: 1,
      phases: [
        {
          name: "phase",
          complete_when: "any_fired",
          skills: [
            {
              skill_id: "sk1",
              priority: 1,
              label: "",
              condition_expr: null,
              start_expr: null,
              complete_expr: null,
              override_cast_ms: null,
            },
          ],
        },
      ],
    },
  ];
  return profile;
}

function enginePreflightReport(ready: boolean): EnginePreflightReport {
  return {
    ready,
    engine_running: false,
    profile_name: "default",
    exec_enabled: ready,
    rotation_count: 1,
    skill_count: ready ? 1 : 0,
    point_count: 0,
    executable_slot_count: ready ? 1 : 0,
    error: ready ? null : "default rotation has no executable enabled skill slots",
  };
}

function captureDiagnosticsResult(): CaptureDiagnosticsResult {
  return {
    monitor_count: 1,
    monitors: ["primary"],
    cursor_x: 10,
    cursor_y: 20,
    cursor_monitor: "primary",
    sample: {
      monitor: "primary",
      x: 10,
      y: 20,
      r: 1,
      g: 2,
      b: 3,
      hex: "#010203",
    },
    sample_error: null,
  };
}

function hotkeyDiagnosticsResult(): HotkeyDiagnosticsResult {
  return {
    toggle_hotkey: "F9",
    pick_hotkey: "F8",
    toggle_registered: true,
    pick_registered: true,
    toggle_callback_count: 1,
    pick_callback_count: 2,
    last_toggle_callback_at: "2026-06-08T00:00:00.000Z",
    last_pick_callback_at: "2026-06-08T00:00:01.000Z",
    conflict: false,
  };
}

describe("desktop IPC smoke", () => {
  it("skips simulator IPC when the profile is not runnable", async () => {
    const simulateRotation = vi.fn();
    const simulateRotationWithPixels = vi.fn();

    const steps = await runDesktopIpcSmoke({
      loadProfile: async () => createDefaultProfile(),
      simulateRotation,
      simulateRotationWithPixels,
      buildPixelOverrides: () => [],
    });

    expect(steps.map((step) => step.status)).toEqual([
      "passed",
      "passed",
      "passed",
      "skipped",
      "skipped",
      "skipped",
      "skipped",
      "skipped",
    ]);
    expect(simulateRotation).not.toHaveBeenCalled();
    expect(simulateRotationWithPixels).not.toHaveBeenCalled();
  });

  it("runs both simulator IPC checks for runnable profiles", async () => {
    const simulateRotation = vi.fn(async () => ({ events: [{ skillId: "sk1" }] as any[] }));
    const simulateRotationWithPixels = vi.fn(async () => ({ events: [] }));
    const enginePreflight = vi.fn(async () => enginePreflightReport(true));
    const captureDiagnostics = vi.fn(async () => captureDiagnosticsResult());
    const hotkeyDiagnostics = vi.fn(async () => hotkeyDiagnosticsResult());

    const steps = await runDesktopIpcSmoke({
      loadProfile: async () => executableProfile(),
      simulateRotation,
      simulateRotationWithPixels,
      buildPixelOverrides: () => [{ monitor: "primary", x: 0, y: 0, r: 1, g: 2, b: 3 }],
      enginePreflight,
      captureDiagnostics,
      hotkeyDiagnostics,
    });

    expect(steps.map((step) => step.status)).toEqual([
      "passed",
      "passed",
      "passed",
      "passed",
      "passed",
      "passed",
      "passed",
      "passed",
    ]);
    expect(enginePreflight).toHaveBeenCalledTimes(1);
    expect(captureDiagnostics).toHaveBeenCalledTimes(1);
    expect(hotkeyDiagnostics).toHaveBeenCalledTimes(1);
    expect(simulateRotation).toHaveBeenCalledTimes(1);
    expect(simulateRotationWithPixels).toHaveBeenCalledWith([
      { monitor: "primary", x: 0, y: 0, r: 1, g: 2, b: 3 },
    ]);
  });

  it("runs fixture profile IPC checks even when the default profile is not runnable", async () => {
    const simulateRotation = vi.fn();
    const simulateRotationWithPixels = vi.fn();
    const simulateProfileRotation = vi.fn(async () => ({ events: [] }));
    const simulateProfileRotationWithPixels = vi.fn(async () => ({
      events: [{ skillId: "smoke-skill" }] as any[],
    }));
    const simulateIpcSmokeFixture = vi.fn(async () => ({
      profile_id: "ipc-smoke",
      direct_events: 1,
      pixel_events: 1,
    }));
    const enginePreflight = vi.fn(async () => enginePreflightReport(false));
    const captureDiagnostics = vi.fn(async () => captureDiagnosticsResult());
    const hotkeyDiagnostics = vi.fn(async () => hotkeyDiagnosticsResult());

    const steps = await runDesktopIpcSmoke({
      loadProfile: async () => createDefaultProfile(),
      simulateRotation,
      simulateRotationWithPixels,
      buildPixelOverrides: (profile) =>
        profile.points.points.map((point) => ({
          monitor: point.monitor,
          x: point.vx,
          y: point.vy,
          r: point.color.r,
          g: point.color.g,
          b: point.color.b,
        })),
      createSmokeProfile: createIpcSmokeProfile,
      simulateProfileRotation,
      simulateProfileRotationWithPixels,
      simulateIpcSmokeFixture,
      enginePreflight,
      captureDiagnostics,
      hotkeyDiagnostics,
    });

    expect(steps.map((step) => [step.id, step.status])).toEqual([
      ["profile_load", "passed"],
      ["profile_json_roundtrip", "passed"],
      ["profile_validate_save", "passed"],
      ["engine_preflight", "passed"],
      ["capture_diagnostics", "passed"],
      ["hotkey_diagnostics", "passed"],
      ["simulate_rotation", "skipped"],
      ["simulate_rotation_with_pixels", "skipped"],
      ["smoke_profile_validate", "passed"],
      ["smoke_profile_simulate", "passed"],
      ["smoke_profile_simulate_with_pixels", "passed"],
      ["backend_smoke_fixture", "passed"],
    ]);
    expect(simulateRotation).not.toHaveBeenCalled();
    expect(simulateRotationWithPixels).not.toHaveBeenCalled();
    expect(simulateProfileRotation).toHaveBeenCalledWith(expect.objectContaining({
      meta: expect.objectContaining({ profile_id: "ipc-smoke" }),
    }));
    expect(simulateProfileRotationWithPixels).toHaveBeenCalledWith(
      expect.objectContaining({
        meta: expect.objectContaining({ profile_id: "ipc-smoke" }),
      }),
      [{ monitor: "primary", x: 10, y: 20, r: 12, g: 34, b: 56 }]
    );
    expect(simulateIpcSmokeFixture).toHaveBeenCalledTimes(1);
  });

  it("marks fixture IPC checks as skipped when profile IPC deps are unavailable", async () => {
    const steps = await runDesktopIpcSmoke({
      loadProfile: async () => createDefaultProfile(),
      simulateRotation: vi.fn(),
      simulateRotationWithPixels: vi.fn(),
      buildPixelOverrides: () => [],
      createSmokeProfile: createIpcSmokeProfile,
    });

    expect(steps.map((step) => [step.id, step.status])).toEqual([
      ["profile_load", "passed"],
      ["profile_json_roundtrip", "passed"],
      ["profile_validate_save", "passed"],
      ["engine_preflight", "skipped"],
      ["capture_diagnostics", "skipped"],
      ["hotkey_diagnostics", "skipped"],
      ["simulate_rotation", "skipped"],
      ["simulate_rotation_with_pixels", "skipped"],
      ["smoke_profile_validate", "passed"],
      ["smoke_profile_simulate", "skipped"],
      ["smoke_profile_simulate_with_pixels", "skipped"],
      ["backend_smoke_fixture", "skipped"],
    ]);
  });

  it("stops immediately when profile loading fails", async () => {
    const steps = await runDesktopIpcSmoke({
      loadProfile: async () => {
        throw new Error("load failed");
      },
      simulateRotation: vi.fn(),
      simulateRotationWithPixels: vi.fn(),
      buildPixelOverrides: () => [],
    });

    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({ id: "profile_load", status: "failed" });
  });

  it("exports a copyable smoke report JSON", () => {
    const json = ipcSmokeDebugJson([
      { id: "a", label: "A", status: "passed", detail: "ok" },
      { id: "b", label: "B", status: "skipped", detail: "no runtime" },
      { id: "c", label: "C", status: "failed", detail: "bad" },
    ]);

    const parsed = JSON.parse(json);

    expect(parsed.summary).toEqual({
      total: 3,
      passed: 1,
      failed: 1,
      skipped: 1,
    });
    expect(parsed.steps).toHaveLength(3);
    expect(parsed.generatedAt).toEqual(expect.any(String));
  });
});
