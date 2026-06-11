# Progress

## Goal

Remove production `console.error` / `console.warn` usage from user-facing frontend flows.

## Done

- Added `src/utils/app-message.ts` as the shared app message event helper.
- Updated global hotkey flows to emit `app:message` instead of logging warnings.
- Removed console logging from capture and engine composables.
- Removed console logging from Settings, Skills, Points, Simulator, Cycle Editor, App Layout, Engine Control Bar, and GW2 import flows.
- Converted previously silent profile load failures in Skills and Points pages into user-visible Naive UI messages.

## Files Changed

- `src/utils/app-message.ts`
- `src/composables/useCapture.ts`
- `src/composables/useEngine.ts`
- `src/composables/useHotkeys.ts`
- `src/components/AppLayout.vue`
- `src/components/engine/EngineControlBar.vue`
- `src/components/editor/Gw2ImportDialog.vue`
- `src/views/SettingsPage.vue`
- `src/views/SkillsPage.vue`
- `src/views/PointsPage.vue`
- `src/views/SimulatorPage.vue`
- `src/views/CycleEditorPage.vue`

## Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test`
- `pnpm.cmd build`
- `rg -n "console\\.(error|warn|log)" src`

## Risks

- Some visible messages still inherit existing Chinese copy from the current UI and can be polished separately.
- `CycleExecutor` structural splitting is left for a separate backend-focused change.
