export type DebugRunStatus = "idle" | "running" | "completed" | "failed" | "stopped";

export interface DebugRunStartedPayload {
  run_id: string;
  start_phase_index: number;
  end_phase_index: number;
  started_at_ms: number;
}

export interface DebugRunEventPayload {
  run_id: string;
  ts_ms: number;
  phase_index: number;
  phase_name: string;
  skill_id: string;
  skill_name: string;
  key: string;
  event: string;
  outcome: string;
  reason: string;
}

export interface DebugRunFinishedPayload {
  run_id: string;
  status: "completed" | "failed" | "stopped";
  reason: string;
  elapsed_ms: number;
  total_events: number;
}
