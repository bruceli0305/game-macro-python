// 引擎 IPC 封装 — 接入 Tauri invoke/listen

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { useEngineStore } from "../stores/engine";
import type { EngineRuntimeSnapshot, SkillAttemptStage } from "../types/engine";
import type { Profile } from "../types/profile";

let unlistenTick: UnlistenFn | null = null;
let unlistenRuntime: UnlistenFn | null = null;
let unlistenLog: UnlistenFn | null = null;
let unlistenStarted: UnlistenFn | null = null;
let unlistenStopped: UnlistenFn | null = null;

function cleanupEngineListeners() {
  unlistenTick?.();
  unlistenTick = null;
  unlistenRuntime?.();
  unlistenRuntime = null;
  unlistenLog?.();
  unlistenLog = null;
  unlistenStarted?.();
  unlistenStarted = null;
  unlistenStopped?.();
  unlistenStopped = null;
}

export function useEngine() {
  const store = useEngineStore();

  async function start(): Promise<void> {
    try {
      cleanup();
      store.clearLog();

      // 先订阅事件
      unlistenTick = await listen<EngineTickPayload>("engine:tick", (event) => {
        store.setRunning(true);
        store.currentPhase = event.payload.phase_index;
        store.cycleCount = event.payload.cycle_count;
        store.updateSkillState(event.payload.skill_id, {
          skillId: event.payload.skill_id,
          state: event.payload.outcome === "Success" ? "SUCCESS" : "IDLE",
          success: 0,
          fail: 0,
          lastAttemptMs: Date.now(),
        });
      });

      unlistenLog = await listen<EngineLogPayload>("engine:log", (event) => {
        store.appendLog({
          tsMs: event.payload.ts_ms,
          kind: "skill",
          outcome: event.payload.outcome,
          phaseIndex: 0,
          phaseName: event.payload.phase_name,
          skillId: event.payload.skill_id,
          skillName: event.payload.skill_name,
          reason: event.payload.reason,
          detail: event.payload.event,
        });
      });

      unlistenRuntime = await listen<EngineRuntimePayload>("engine:runtime", (event) => {
        store.applyRuntimeSnapshot(toRuntimeSnapshot(event.payload));
      });

      unlistenStarted = await listen("engine:started", () => {
        store.setRunning(true);
      });

      unlistenStopped = await listen("engine:stopped", () => {
        store.setRunning(false);
      });

      await invoke("engine_start");
      store.setRunning(true);
    } catch (e) {
      console.error("engine_start failed:", e);
      throw e;
    }
  }

  async function stop(): Promise<void> {
    try {
      await invoke("engine_stop");
    } catch (e) {
      console.error("engine_stop failed:", e);
    }
  }

  async function preflight(): Promise<EnginePreflightReport> {
    return await invoke<EnginePreflightReport>("engine_preflight");
  }

  async function simulateRotation(): Promise<SimulationResult> {
    const json = await invoke<string>("simulate_rotation");
    return JSON.parse(json) as SimulationResult;
  }

  async function simulateRotationWithPixels(
    pixelOverrides: PixelOverride[]
  ): Promise<SimulationResult> {
    const json = await invoke<string>("simulate_rotation_with_pixels", { pixelOverrides });
    return JSON.parse(json) as SimulationResult;
  }

  async function simulateProfileRotation(profile: Profile): Promise<SimulationResult> {
    const content = JSON.stringify(profile);
    const json = await invoke<string>("simulate_profile_rotation", { content });
    return JSON.parse(json) as SimulationResult;
  }

  async function simulateProfileRotationWithPixels(
    profile: Profile,
    pixelOverrides: PixelOverride[]
  ): Promise<SimulationResult> {
    const content = JSON.stringify(profile);
    const json = await invoke<string>("simulate_profile_rotation_with_pixels", {
      content,
      pixelOverrides,
    });
    return JSON.parse(json) as SimulationResult;
  }

  async function simulateIpcSmokeFixture(): Promise<IpcSmokeFixtureResult> {
    const json = await invoke<string>("simulate_ipc_smoke_fixture");
    return JSON.parse(json) as IpcSmokeFixtureResult;
  }

  /** 取消事件监听 */
  function cleanup() {
    cleanupEngineListeners();
  }

  return {
    start,
    stop,
    preflight,
    simulateRotation,
    simulateRotationWithPixels,
    simulateProfileRotation,
    simulateProfileRotationWithPixels,
    simulateIpcSmokeFixture,
    cleanup,
    store,
  };
}

interface EngineTickPayload {
  total_executed: number;
  cycle_count: number;
  phase_index: number;
  phase_name: string;
  skill_id: string;
  skill_name: string;
  outcome: string;
}

interface EngineLogPayload {
  ts_ms: number;
  phase_name: string;
  event: string;
  skill_id: string;
  skill_name: string;
  outcome: string;
  reason: string;
}

interface EngineRuntimePayload {
  running: boolean;
  paused: boolean;
  preset_id: string;
  stop_reason: string;
  total_executed: number;
  cycle_count: number;
  phase_index: number;
  phase_name: string;
  uptime_ms: number;
  cast_bar_roi: CastBarRoiRuntimePayload | null;
  skills: SkillRuntimePayload[];
}

interface CastBarRoiRuntimePayload {
  enabled: boolean;
  sample_count: number;
  cache_hit_count: number;
  failed_sample_count: number;
  last_latency_us: number;
  avg_latency_us: number;
  max_latency_us: number;
  last_changed_ratio: number;
  last_border_match_ratio: number;
  last_changed_from_baseline: boolean;
  last_border_visible: boolean;
  last_gone: boolean;
  last_error: string;
}

interface SkillRuntimePayload {
  skill_id: string;
  skill_name: string;
  state: SkillAttemptStage;
  node_exec: number;
  ready_false: number;
  skipped_disabled: number;
  skipped_lock_busy: number;
  attempt_started: number;
  key_sent_ok: number;
  cast_started: number;
  success: number;
  fail: number;
}

function toRuntimeSnapshot(payload: EngineRuntimePayload): EngineRuntimeSnapshot {
  return {
    running: payload.running,
    paused: payload.paused,
    presetId: payload.preset_id,
    stopReason: payload.stop_reason,
    totalExecuted: payload.total_executed,
    cycleCount: payload.cycle_count,
    phaseIndex: payload.phase_index,
    phaseName: payload.phase_name,
    uptimeMs: payload.uptime_ms,
    castBarRoi: payload.cast_bar_roi ? toCastBarRoiStats(payload.cast_bar_roi) : null,
    skills: payload.skills.map((skill) => ({
      skillId: skill.skill_id,
      skillName: skill.skill_name,
      state: skill.state,
      nodeExec: skill.node_exec,
      readyFalse: skill.ready_false,
      skippedDisabled: skill.skipped_disabled,
      skippedLockBusy: skill.skipped_lock_busy,
      attemptStarted: skill.attempt_started,
      keySentOk: skill.key_sent_ok,
      castStarted: skill.cast_started,
      success: skill.success,
      fail: skill.fail,
      lastAttemptMs: payload.uptime_ms,
    })),
  };
}

function toCastBarRoiStats(payload: CastBarRoiRuntimePayload) {
  return {
    enabled: payload.enabled,
    sampleCount: payload.sample_count,
    cacheHitCount: payload.cache_hit_count,
    failedSampleCount: payload.failed_sample_count,
    lastLatencyUs: payload.last_latency_us,
    avgLatencyUs: payload.avg_latency_us,
    maxLatencyUs: payload.max_latency_us,
    lastChangedRatio: payload.last_changed_ratio,
    lastBorderMatchRatio: payload.last_border_match_ratio,
    lastChangedFromBaseline: payload.last_changed_from_baseline,
    lastBorderVisible: payload.last_border_visible,
    lastGone: payload.last_gone,
    lastError: payload.last_error,
  };
}

export interface SimulationEvent {
  index: number;
  timeMs: number;
  phase: string;
  event: string;
  skillId: string;
  skillName: string;
  outcome: string;
  castMs: number;
  cdMs: number;
  reason: string;
}

export interface SimulationResult {
  events: SimulationEvent[];
}

export interface PixelOverride {
  monitor: string;
  x: number;
  y: number;
  r: number;
  g: number;
  b: number;
}

export interface IpcSmokeFixtureResult {
  profile_id: string;
  direct_events: number;
  pixel_events: number;
}

export interface EnginePreflightReport {
  ready: boolean;
  engine_running: boolean;
  profile_name: string;
  exec_enabled: boolean;
  rotation_count: number;
  skill_count: number;
  point_count: number;
  executable_slot_count: number;
  error: string | null;
}
