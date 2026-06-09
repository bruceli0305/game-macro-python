export type SkillAttemptStage =
  | "IDLE"
  | "PREPARING"
  | "START_WAIT"
  | "CASTING"
  | "COMPLETE_WAIT"
  | "SUCCESS"
  | "FAILED"
  | "STOPPED";

export interface SkillRuntimeState {
  skillId: string;
  skillName: string;
  state: SkillAttemptStage;
  nodeExec: number;
  readyFalse: number;
  skippedDisabled: number;
  skippedLockBusy: number;
  attemptStarted: number;
  keySentOk: number;
  castStarted: number;
  success: number;
  fail: number;
  lastAttemptMs: number;
}

export interface EngineRuntimeSnapshot {
  running: boolean;
  paused: boolean;
  presetId: string;
  stopReason: string;
  totalExecuted: number;
  cycleCount: number;
  phaseIndex: number;
  phaseName: string;
  uptimeMs: number;
  castBarRoi: CastBarRoiRuntimeStats | null;
  skills: SkillRuntimeState[];
}

export interface CastBarRoiRuntimeStats {
  enabled: boolean;
  sampleCount: number;
  cacheHitCount: number;
  failedSampleCount: number;
  lastLatencyUs: number;
  avgLatencyUs: number;
  maxLatencyUs: number;
  lastChangedRatio: number;
  lastBorderMatchRatio: number;
  lastChangedFromBaseline: boolean;
  lastBorderVisible: boolean;
  lastGone: boolean;
  lastError: string;
}

export interface ExecLogEntry {
  tsMs: number;
  kind: "skill" | "gateway" | "schedule" | "error";
  outcome: string;
  phaseIndex: number;
  phaseName: string;
  skillId: string;
  skillName: string;
  reason: string;
  detail: string;
}
