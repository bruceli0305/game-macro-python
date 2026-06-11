# Loop Debug Panel Final Vision

## Goal

The final debug panel should become the compact operational console for cycle authoring, execution diagnosis, and phase tuning. It should stay small enough to use over the game, but powerful enough to explain why a rotation did or did not execute.

## Core Principles

- Always visible while playing: the debug window remains always-on-top.
- Small surface, high signal: logs and state summaries matter more than broad dashboards.
- Structured data first: frontend should display backend event fields, not parse free-form text.
- No gameplay bypass: debugging still uses the same screen sampling, AST evaluation, cooldown, attempt, and key sending paths as normal execution.
- No hidden state mutation: debug execution should not corrupt active profile data or normal engine task state.

## Final Capability Set

### Run Modes

- Single phase once.
- Continuous phase range once.
- Continuous phase range loop.
- Single tick / step mode.
- Pause and resume.
- Stop and reset.

### Phase Controls

- Start phase selection.
- End phase selection.
- Current phase display.
- Optional phase pinning.
- Optional transition override for diagnosis.

### Logging

- Key attempt logs.
- Phase enter / phase complete logs.
- Condition evaluation logs.
- Readiness evaluation logs.
- Start confirmation logs.
- Complete confirmation logs.
- Observer lane action logs.
- Assist lane interrupt logs.
- Runtime marker / counter / timer mutation logs.

### Filters

- Filter by phase.
- Filter by skill.
- Filter by event type.
- Filter by outcome.
- Toggle verbose condition logs.
- Toggle observer / assist lane logs.

### Inspection

- Current runtime state summary.
- Skill metrics summary.
- Active marker values.
- Active counter values.
- Active timers.
- Last sampled pixel values for referenced probes.
- Cast-bar ROI status and sampling stats.

### Export

- Copy current run log as JSON.
- Copy current run log as text.
- Save debug session file.
- Attach profile hash or profile name to exported sessions.

### UX

- Always-on-top independent window.
- Small default window.
- Resizable layout.
- Dense log rows.
- Keyboard shortcuts for run, stop, clear, and step.
- Persist last window position and size.
- Reopen existing window rather than spawning duplicates.

## Suggested Final Layout

```text
┌────────────────────────────────────────────┐
│ 循环调试                    ● 置顶  ⚙  ✕   │
├────────────────────────────────────────────┤
│ Mode: [Once ▼]  Range: [P1 ▼] -> [P2 ▼]    │
│ [Run] [Step] [Pause] [Stop] [Clear]        │
├────────────────────────────────────────────┤
│ Phase P1 | elapsed 1240ms | attempts 2/5   │
│ markers: fire=on | counter burst=2         │
├────────────────────────────────────────────┤
│ Filters: [All] [Fail] [Skip] [Keys] [AST]  │
├────────────────────────────────────────────┤
│ 12ms  SUCCESS P1 火焰协调 key=F1           │
│ 25ms  AST     P1 龙牙 condition=false      │
│ 328ms SKIP    P1 龙牙 readiness_false      │
│ 710ms FAIL    P1 火焰吐息 complete_timeout │
└────────────────────────────────────────────┘
```

## Backend Direction

- Keep debug execution as a separate task domain from normal engine execution.
- Share the same compiled runtime config and execution primitives.
- Emit structured events from a debug-specific event adapter.
- Keep cancellation explicit with a debug task handle.
- Add bounded runtime protections for loop and step modes.

## Frontend Direction

- Keep the debug panel out of `CycleEditorPage.vue`.
- Use a dedicated route and page: `/debug-panel`.
- Use a dedicated composable: `useDebugRun`.
- Keep log rendering virtualizable if event volume grows.
- Use local-only UI state for filters, expanded rows, and selected event.

## Long-Term Acceptance Criteria

- A user can explain every skipped or failed skill from the panel alone.
- A user can compare runtime conditions with expected profile logic.
- A user can run one phase, a phase range, or step tick-by-tick without starting the normal engine.
- Debug events can be exported and replayed or inspected outside the app.
- The panel remains usable over the game at small size.
