export interface SimulationDebugEvent {
  event: string;
  outcome: string;
  reason: string;
  timeMs: number;
  skillId: string;
}

export interface SimulationSummary {
  total: number;
  executed: number;
  skipped: number;
  success: number;
  notReady: number;
  failed: number;
  durationMs: number;
  uniqueSkills: number;
  topReasons: Array<{ reason: string; count: number }>;
}

export function summarizeSimulation(events: SimulationDebugEvent[]): SimulationSummary {
  const reasonCounts = new Map<string, number>();
  const skillIds = new Set<string>();

  let executed = 0;
  let skipped = 0;
  let success = 0;
  let notReady = 0;
  let failed = 0;
  let durationMs = 0;

  for (const event of events) {
    if (event.event === "skip") skipped += 1;
    else executed += 1;

    if (event.outcome === "Success") success += 1;
    else if (event.outcome === "NOT_READY") notReady += 1;
    else failed += 1;

    if (event.reason) {
      reasonCounts.set(event.reason, (reasonCounts.get(event.reason) || 0) + 1);
    }
    if (event.skillId) skillIds.add(event.skillId);
    durationMs = Math.max(durationMs, event.timeMs);
  }

  const topReasons = [...reasonCounts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason))
    .slice(0, 5);

  return {
    total: events.length,
    executed,
    skipped,
    success,
    notReady,
    failed,
    durationMs,
    uniqueSkills: skillIds.size,
    topReasons,
  };
}

export function simulationDebugJson(events: SimulationDebugEvent[]): string {
  return JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      summary: summarizeSimulation(events),
      events,
    },
    null,
    2
  );
}
