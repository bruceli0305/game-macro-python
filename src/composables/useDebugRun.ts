import { computed, readonly, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  DebugRunEventPayload,
  DebugRunFinishedPayload,
  DebugRunStartedPayload,
  DebugRunStatus,
} from "../types/debug-run";

let listenersReady: Promise<void> | null = null;
let unlisteners: UnlistenFn[] = [];

const status = ref<DebugRunStatus>("idle");
const runId = ref("");
const logs = ref<DebugRunEventPayload[]>([]);
const latestError = ref("");
const elapsedMs = ref(0);
const startPhaseIndex = ref(0);
const endPhaseIndex = ref(0);

const isRunning = computed(() => status.value === "running");

function applyStarted(payload: DebugRunStartedPayload) {
  runId.value = payload.run_id;
  startPhaseIndex.value = payload.start_phase_index;
  endPhaseIndex.value = payload.end_phase_index;
  elapsedMs.value = 0;
  latestError.value = "";
  logs.value = [];
  status.value = "running";
}

function applyEvent(payload: DebugRunEventPayload) {
  if (runId.value && payload.run_id !== runId.value) return;
  logs.value = [...logs.value, payload];
  elapsedMs.value = Math.max(elapsedMs.value, payload.ts_ms);
}

function applyFinished(payload: DebugRunFinishedPayload) {
  if (runId.value && payload.run_id !== runId.value) return;
  status.value = payload.status;
  elapsedMs.value = payload.elapsed_ms;
  latestError.value = payload.status === "failed" ? payload.reason : "";
}

async function ensureListeners() {
  if (listenersReady) return listenersReady;

  listenersReady = Promise.all([
    listen<DebugRunStartedPayload>("debug:run-started", (event) => applyStarted(event.payload)),
    listen<DebugRunEventPayload>("debug:run-event", (event) => applyEvent(event.payload)),
    listen<DebugRunFinishedPayload>("debug:run-finished", (event) => applyFinished(event.payload)),
    listen<DebugRunFinishedPayload>("debug:run-stopped", (event) => applyFinished(event.payload)),
    listen<DebugRunFinishedPayload>("debug:run-failed", (event) => applyFinished(event.payload)),
  ]).then((next) => {
    unlisteners = next;
  });

  return listenersReady;
}

export function disposeDebugRunListeners() {
  for (const unlisten of unlisteners) unlisten();
  unlisteners = [];
  listenersReady = null;
}

export function clearDebugRunState() {
  status.value = "idle";
  runId.value = "";
  logs.value = [];
  latestError.value = "";
  elapsedMs.value = 0;
  startPhaseIndex.value = 0;
  endPhaseIndex.value = 0;
}

export function appendDebugRunEventForTest(payload: DebugRunEventPayload) {
  applyEvent(payload);
}

export function finishDebugRunForTest(payload: DebugRunFinishedPayload) {
  applyFinished(payload);
}

export function startDebugRunForTest(payload: DebugRunStartedPayload) {
  applyStarted(payload);
}

export function useDebugRun() {
  async function openPanel(): Promise<string> {
    return await invoke<string>("open_debug_panel_window");
  }

  async function runOnce(start: number, end: number): Promise<string> {
    await ensureListeners();
    return await invoke<string>("debug_run_once", {
      startPhaseIndex: start,
      endPhaseIndex: end,
    });
  }

  async function stop(): Promise<void> {
    await invoke("debug_stop_run");
  }

  function clearLogs() {
    logs.value = [];
    latestError.value = "";
    if (status.value !== "running") {
      status.value = "idle";
      runId.value = "";
      elapsedMs.value = 0;
    }
  }

  return {
    status: readonly(status),
    isRunning,
    runId: readonly(runId),
    logs: readonly(logs),
    latestError: readonly(latestError),
    elapsedMs: readonly(elapsedMs),
    startPhaseIndex: readonly(startPhaseIndex),
    endPhaseIndex: readonly(endPhaseIndex),
    openPanel,
    runOnce,
    stop,
    clearLogs,
    ensureListeners,
  };
}
