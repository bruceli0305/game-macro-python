# Progress

## Goal

Create a built-in role profile for Snow Crows Condition Weaver - Pistol & Dagger and express the published rotation as a maintainable state-machine preset.

## Done

- Added `condition_weaver_pistol_dagger` to role profile seeds.
- Added a Snow Crows-inspired cycle preset with:
  - Preparation
  - Weave Self Rotation
  - normal Loop
  - priority insert assist lane for 8, 9, 4, and 5
  - auto-attack filler assist lane
- Added Elementalist attunement skill seeds for F1-F4.
- Added tests covering the new role profile and cycle preset.

## Files Changed

- `src/assets/json/role-profile-seeds.json`
- `src/assets/json/cycle-presets.json`
- `src/utils/role-profile-templates.ts`
- `src/utils/cycle-presets.ts`
- `src/__tests__/role-profile-templates.test.ts`
- `src/__tests__/cycle-presets.test.ts`

## Root Cause / Key Decision

Snow Crows provides a rotation structure rather than screen-pixel data. The preset therefore maps the published stage order into phases and uses placeholder pixel seeds that must be re-picked for the user's UI.

## Logs / Tests

- `node -e "JSON.parse(...role-profile-seeds.json); JSON.parse(...cycle-presets.json)"`
- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test -- src/__tests__/cycle-presets.test.ts src/__tests__/role-profile-templates.test.ts src/__tests__/profile-validation.test.ts`

## Risks

- Skill names from Snow Crows icons were not available as plain text in the page markup; this preset uses key-slot names such as `Pistol 2`, `Dagger 4`, and `Utility 8`.
- The preset models attunement transitions through F1-F4 skill slots and an `attunement` marker; real dual-attunement verification will need user-picked pixels or a future attunement detector.
- The priority lane expresses the page's "use 8, 9, 4, 5 when available" note, but exact animation locks and encounter-specific delays still need tuning.

## Next Step

Run profile validation, then verify in the editor that switching to the built-in Weaver role loads the expected phases and lanes.
