import { validateProfileForRun, validateProfileForSave } from "./profile-validation";
import type {
  EnginePreflightReport,
  IpcSmokeFixtureResult,
  PixelOverride,
  SimulationResult,
} from "../composables/useEngine";
import type { CaptureDiagnosticsResult } from "../composables/useCapture";
import type { HotkeyDiagnosticsResult } from "../composables/useHotkeys";
import type { Profile } from "../types/profile";

export type IpcSmokeStatus = "passed" | "failed" | "skipped";

export interface IpcSmokeStep {
  id: string;
  label: string;
  status: IpcSmokeStatus;
  detail: string;
}

export interface IpcSmokeSummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
}

export interface DesktopIpcSmokeDeps {
  loadProfile: () => Promise<Profile>;
  simulateRotation: () => Promise<SimulationResult>;
  simulateRotationWithPixels: (pixelOverrides: PixelOverride[]) => Promise<SimulationResult>;
  buildPixelOverrides: (profile: Profile) => PixelOverride[];
  createSmokeProfile?: () => Profile;
  simulateProfileRotation?: (profile: Profile) => Promise<SimulationResult>;
  simulateProfileRotationWithPixels?: (
    profile: Profile,
    pixelOverrides: PixelOverride[]
  ) => Promise<SimulationResult>;
  simulateIpcSmokeFixture?: () => Promise<IpcSmokeFixtureResult>;
  enginePreflight?: () => Promise<EnginePreflightReport>;
  captureDiagnostics?: () => Promise<CaptureDiagnosticsResult | null>;
  hotkeyDiagnostics?: () => Promise<HotkeyDiagnosticsResult>;
}

function eventCount(result: SimulationResult): number {
  return Array.isArray(result.events) ? result.events.length : 0;
}

function captureDiagnosticsDetail(result: CaptureDiagnosticsResult): string {
  if (result.sample) {
    return `${result.cursor_monitor} (${result.cursor_x},${result.cursor_y}) ${result.sample.hex}`;
  }
  return result.sample_error || "sample failed";
}

function hotkeyDiagnosticsDetail(result: HotkeyDiagnosticsResult): string {
  return `toggle=${result.toggle_hotkey}:${result.toggle_registered}/callbacks=${result.toggle_callback_count}, pick=${result.pick_hotkey}:${result.pick_registered}/callbacks=${result.pick_callback_count}`;
}

function profileRoundTripDetail(profile: Profile): string {
  const content = JSON.stringify(profile);
  const parsed = JSON.parse(content) as Profile;
  const sameIdentity =
    parsed.meta.profile_id === profile.meta.profile_id &&
    parsed.schema_version === profile.schema_version;
  const sameSections =
    parsed.skills.skills.length === profile.skills.skills.length &&
    parsed.points.points.length === profile.points.points.length &&
    parsed.rotations.length === profile.rotations.length;

  if (!sameIdentity || !sameSections) {
    throw new Error("profile JSON round-trip changed profile shape");
  }

  return `bytes=${content.length}, skills=${parsed.skills.skills.length}, points=${parsed.points.points.length}, rotations=${parsed.rotations.length}`;
}

export function summarizeIpcSmokeSteps(steps: IpcSmokeStep[]): IpcSmokeSummary {
  return {
    total: steps.length,
    passed: steps.filter((step) => step.status === "passed").length,
    failed: steps.filter((step) => step.status === "failed").length,
    skipped: steps.filter((step) => step.status === "skipped").length,
  };
}

export function ipcSmokeDebugJson(steps: IpcSmokeStep[]): string {
  return JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      summary: summarizeIpcSmokeSteps(steps),
      steps,
    },
    null,
    2
  );
}

export async function runDesktopIpcSmoke(
  deps: DesktopIpcSmokeDeps
): Promise<IpcSmokeStep[]> {
  const steps: IpcSmokeStep[] = [];
  let profile: Profile | null = null;

  try {
    profile = await deps.loadProfile();
    steps.push({
      id: "profile_load",
      label: "加载默认配置",
      status: "passed",
      detail: `skills=${profile.skills.skills.length}, points=${profile.points.points.length}, rotations=${profile.rotations.length}`,
    });
  } catch (error) {
    steps.push({
      id: "profile_load",
      label: "加载默认配置",
      status: "failed",
      detail: String(error || "profile load failed"),
    });
    return steps;
  }

  try {
    steps.push({
      id: "profile_json_roundtrip",
      label: "配置 JSON 往返",
      status: "passed",
      detail: profileRoundTripDetail(profile),
    });
  } catch (error) {
    steps.push({
      id: "profile_json_roundtrip",
      label: "配置 JSON 往返",
      status: "failed",
      detail: String(error || "profile JSON round-trip failed"),
    });
  }

  const saveIssues = validateProfileForSave(profile);
  steps.push({
    id: "profile_validate_save",
    label: "保存级配置校验",
    status: saveIssues.length === 0 ? "passed" : "failed",
    detail: saveIssues.length === 0 ? "ok" : `${saveIssues.length} issues`,
  });

  if (!deps.enginePreflight) {
    steps.push({
      id: "engine_preflight",
      label: "后端启动预检",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
  } else {
    try {
      const report = await deps.enginePreflight();
      steps.push({
        id: "engine_preflight",
        label: "后端启动预检",
        status: "passed",
        detail: report.ready
          ? `ready=true, skills=${report.skill_count}, slots=${report.executable_slot_count}`
          : `ready=false, ${report.error || "not ready"}`,
      });
    } catch (error) {
      steps.push({
        id: "engine_preflight",
        label: "后端启动预检",
        status: "failed",
        detail: String(error || "engine_preflight failed"),
      });
    }
  }

  if (!deps.captureDiagnostics) {
    steps.push({
      id: "capture_diagnostics",
      label: "取色诊断 IPC",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
  } else {
    try {
      const result = await deps.captureDiagnostics();
      if (!result) {
        steps.push({
          id: "capture_diagnostics",
          label: "取色诊断 IPC",
          status: "failed",
          detail: "capture_diagnostics returned empty result",
        });
      } else {
        steps.push({
          id: "capture_diagnostics",
          label: "取色诊断 IPC",
          status: result.sample ? "passed" : "failed",
          detail: captureDiagnosticsDetail(result),
        });
      }
    } catch (error) {
      steps.push({
        id: "capture_diagnostics",
        label: "取色诊断 IPC",
        status: "failed",
        detail: String(error || "capture_diagnostics failed"),
      });
    }
  }

  if (!deps.hotkeyDiagnostics) {
    steps.push({
      id: "hotkey_diagnostics",
      label: "热键注册诊断",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
  } else {
    try {
      const result = await deps.hotkeyDiagnostics();
      steps.push({
        id: "hotkey_diagnostics",
        label: "热键注册诊断",
        status: !result.conflict && result.toggle_registered && result.pick_registered
          ? "passed"
          : "failed",
        detail: result.conflict ? "hotkey conflict" : hotkeyDiagnosticsDetail(result),
      });
    } catch (error) {
      steps.push({
        id: "hotkey_diagnostics",
        label: "热键注册诊断",
        status: "failed",
        detail: String(error || "hotkey diagnostics failed"),
      });
    }
  }

  const runIssues = validateProfileForRun(profile);
  if (runIssues.length > 0) {
    steps.push({
      id: "simulate_rotation",
      label: "推演 IPC",
      status: "skipped",
      detail: `${runIssues.length} run-readiness issues`,
    });
    steps.push({
      id: "simulate_rotation_with_pixels",
      label: "模拟像素推演 IPC",
      status: "skipped",
      detail: `${runIssues.length} run-readiness issues`,
    });
  } else {
    try {
      const result = await deps.simulateRotation();
      steps.push({
        id: "simulate_rotation",
        label: "推演 IPC",
        status: "passed",
        detail: `events=${eventCount(result)}`,
      });
    } catch (error) {
      steps.push({
        id: "simulate_rotation",
        label: "推演 IPC",
        status: "failed",
        detail: String(error || "simulate_rotation failed"),
      });
    }

    try {
      const result = await deps.simulateRotationWithPixels(deps.buildPixelOverrides(profile));
      steps.push({
        id: "simulate_rotation_with_pixels",
        label: "模拟像素推演 IPC",
        status: "passed",
        detail: `events=${eventCount(result)}`,
      });
    } catch (error) {
      steps.push({
        id: "simulate_rotation_with_pixels",
        label: "模拟像素推演 IPC",
        status: "failed",
        detail: String(error || "simulate_rotation_with_pixels failed"),
      });
    }
  }

  if (!deps.createSmokeProfile) {
    return steps;
  }

  const smokeProfile = deps.createSmokeProfile();
  const smokeIssues = validateProfileForRun(smokeProfile);
  steps.push({
    id: "smoke_profile_validate",
    label: "样例配置校验",
    status: smokeIssues.length === 0 ? "passed" : "failed",
    detail: smokeIssues.length === 0 ? "ok" : `${smokeIssues.length} issues`,
  });
  if (smokeIssues.length > 0) {
    return steps;
  }

  if (!deps.simulateProfileRotation || !deps.simulateProfileRotationWithPixels) {
    steps.push({
      id: "smoke_profile_simulate",
      label: "样例推演 IPC",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
    steps.push({
      id: "smoke_profile_simulate_with_pixels",
      label: "样例像素推演 IPC",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
  } else {
    try {
      const result = await deps.simulateProfileRotation(smokeProfile);
      steps.push({
        id: "smoke_profile_simulate",
        label: "样例推演 IPC",
        status: "passed",
        detail: `events=${eventCount(result)}`,
      });
    } catch (error) {
      steps.push({
        id: "smoke_profile_simulate",
        label: "样例推演 IPC",
        status: "failed",
        detail: String(error || "simulate_profile_rotation failed"),
      });
    }

    try {
      const result = await deps.simulateProfileRotationWithPixels(
        smokeProfile,
        deps.buildPixelOverrides(smokeProfile)
      );
      steps.push({
        id: "smoke_profile_simulate_with_pixels",
        label: "样例像素推演 IPC",
        status: "passed",
        detail: `events=${eventCount(result)}`,
      });
    } catch (error) {
      steps.push({
        id: "smoke_profile_simulate_with_pixels",
        label: "样例像素推演 IPC",
        status: "failed",
        detail: String(error || "simulate_profile_rotation_with_pixels failed"),
      });
    }
  }

  if (!deps.simulateIpcSmokeFixture) {
    steps.push({
      id: "backend_smoke_fixture",
      label: "后端样例自检",
      status: "skipped",
      detail: "Tauri IPC runtime unavailable",
    });
    return steps;
  }

  try {
    const result = await deps.simulateIpcSmokeFixture();
    steps.push({
      id: "backend_smoke_fixture",
      label: "后端样例自检",
      status: "passed",
      detail: `profile=${result.profile_id}, direct=${result.direct_events}, pixels=${result.pixel_events}`,
    });
  } catch (error) {
    steps.push({
      id: "backend_smoke_fixture",
      label: "后端样例自检",
      status: "failed",
      detail: String(error || "simulate_ipc_smoke_fixture failed"),
    });
  }

  return steps;
}
