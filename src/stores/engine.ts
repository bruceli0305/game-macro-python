import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { SkillRuntimeState, ExecLogEntry, EngineRuntimeSnapshot } from "../types/engine";

export const useEngineStore = defineStore("engine", () => {
  const isRunning = ref(false);
  const isPaused = ref(false);
  const cycleCount = ref(0);
  const currentPhase = ref(0);
  const totalExecuted = ref(0);
  const phaseName = ref("");
  const uptimeMs = ref(0);
  const castBarRoi = ref<EngineRuntimeSnapshot["castBarRoi"]>(null);
  const skills = ref<Map<string, SkillRuntimeState>>(new Map());
  const execLog = ref<ExecLogEntry[]>([]);
  const maxLogEntries = 500;

  function setRunning(running: boolean) {
    isRunning.value = running;
  }

  function setPaused(paused: boolean) {
    isPaused.value = paused;
  }

  function updateSkillState(skillId: string, state: Partial<SkillRuntimeState>) {
    const current = skills.value.get(skillId) || {
      skillId,
      skillName: "",
      state: "IDLE",
      nodeExec: 0,
      readyFalse: 0,
      skippedDisabled: 0,
      skippedLockBusy: 0,
      attemptStarted: 0,
      keySentOk: 0,
      castStarted: 0,
      success: 0,
      fail: 0,
      lastAttemptMs: 0,
    };
    skills.value.set(skillId, { ...current, ...state });
  }

  function applyRuntimeSnapshot(snapshot: EngineRuntimeSnapshot) {
    isRunning.value = snapshot.running;
    isPaused.value = snapshot.paused;
    totalExecuted.value = snapshot.totalExecuted;
    cycleCount.value = snapshot.cycleCount;
    currentPhase.value = snapshot.phaseIndex;
    phaseName.value = snapshot.phaseName;
    uptimeMs.value = snapshot.uptimeMs;
    castBarRoi.value = snapshot.castBarRoi;
    skills.value = new Map(snapshot.skills.map((skill) => [skill.skillId, skill]));
  }

  function appendLog(entry: ExecLogEntry) {
    execLog.value.push(entry);
    if (execLog.value.length > maxLogEntries) {
      execLog.value = execLog.value.slice(-maxLogEntries);
    }
  }

  function clearLog() {
    execLog.value = [];
  }

  function reset() {
    isRunning.value = false;
    isPaused.value = false;
    cycleCount.value = 0;
    currentPhase.value = 0;
    totalExecuted.value = 0;
    phaseName.value = "";
    uptimeMs.value = 0;
    castBarRoi.value = null;
    skills.value.clear();
    execLog.value = [];
  }

  const phaseLabel = computed(() => `Phase ${currentPhase.value + 1}`);
  const skillRows = computed(() =>
    Array.from(skills.value.values()).sort((left, right) => {
      const leftLabel = left.skillName || left.skillId;
      const rightLabel = right.skillName || right.skillId;
      return leftLabel.localeCompare(rightLabel);
    })
  );

  return {
    isRunning, isPaused, cycleCount, currentPhase, totalExecuted, phaseName, uptimeMs, castBarRoi, skills, execLog,
    setRunning, setPaused, updateSkillState, applyRuntimeSnapshot, appendLog, clearLog, reset,
    phaseLabel, skillRows,
  };
});
