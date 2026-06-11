# Loop Debug Panel V1 Requirements

## Goal

Build a small always-on-top debug window for one-shot cycle verification while the game is in focus. V1 is for quickly answering: which phase ran, which skill attempted to send a key, whether it succeeded, and why it failed or skipped.

## User Workflow

1. Open the debug panel from the main app.
2. Pick a start phase.
3. Pick an end phase.
4. Click `Run Once`.
5. Keep the panel visible above the game while the selected phase range executes once.
6. Read the key-attempt log after the run finishes.

## Scope

- Always-on-top independent Tauri window.
- Single run only.
- Continuous phase ranges only, for example `P1` or `P1 -> P2`.
- Uses the active profile and current cycle configuration.
- Emits detailed structured logs for every relevant execution decision.
- Prevents debug run startup while the normal engine is running.
- Prevents starting a second debug run while one debug run is active.

## Non-Goals

- No continuous loop mode.
- No breakpoint support.
- No single-step tick mode.
- No arbitrary non-contiguous phase selection.
- No historical log persistence.
- No charts or large dashboard layout.
- No editing profile data inside the debug panel.

## Window Requirements

- Window label: `debug-panel`.
- Default size: approximately `420 x 560`.
- Resizable: yes.
- Always on top: yes.
- Reopen behavior: if the window already exists, show and focus it instead of creating another window.
- Route: `/debug-panel`.

## UI Layout

```text
┌────────────────────────────────────────────┐
│ 循环调试面板                         ● 置顶 │
├────────────────────────────────────────────┤
│ 阶段范围                                   │
│ [ P1 ▼ ]  ->  [ P1 ▼ ]                     │
│                                            │
│ [Run Once] [Stop] [Clear]    status: idle  │
├────────────────────────────────────────────┤
│ 本次运行                                   │
│ phase: P1                                  │
│ attempts: 2 / 5                            │
│ elapsed: 1240ms                            │
├────────────────────────────────────────────┤
│ 发键记录                                   │
│ SUCCESS P1 火焰协调 key=F1 12ms            │
│ SKIP    P1 龙牙     key=2  readiness false │
│ FAIL    P1 火焰吐息 key=3  complete timeout│
└────────────────────────────────────────────┘
```

## Controls

- `Start Phase`: select the first phase index.
- `End Phase`: select the final phase index.
- `Run Once`: starts one debug run.
- `Stop`: cancels the current debug run.
- `Clear`: clears the visible log list only.

## Log Fields

Each debug log row should include:

- `run_id`
- `ts_ms`
- `phase_index`
- `phase_name`
- `skill_id`
- `skill_name`
- `key`
- `event`
- `outcome`
- `reason`

Expected outcomes:

- `SUCCESS`
- `FAILED`
- `SKIP`
- `NOT_READY`
- `STOPPED`
- `INFO`

Expected reasons include:

- `skill_missing`
- `skill_disabled`
- `condition_false`
- `readiness_false`
- `cooldown_not_ready`
- `start_timeout`
- `complete_timeout`
- `send_key_failed`
- `phase_empty`
- `range_completed`

## Backend Commands

### `open_debug_panel_window`

Opens or focuses the always-on-top debug window.

### `debug_run_once`

Starts a one-shot debug run.

Input:

- `start_phase_index: usize`
- `end_phase_index: usize`

Rules:

- Reject when `start_phase_index > end_phase_index`.
- Reject when either phase index is out of range.
- Reject when the normal engine is running.
- Reject when another debug run is running.

### `debug_stop_run`

Cancels the active debug run if one exists.

## Events

- `debug:run-started`
- `debug:run-event`
- `debug:run-finished`
- `debug:run-stopped`
- `debug:run-failed`

## Acceptance Criteria

- Selecting `P1 -> P1` runs only P1 once.
- Selecting `P1 -> P2` runs P1 and P2 once, then stops.
- The panel stays visible above the game window.
- Every key attempt shows phase, skill, key, outcome, and reason.
- The run ends without entering later phases.
- The normal engine and debug run cannot run concurrently.
