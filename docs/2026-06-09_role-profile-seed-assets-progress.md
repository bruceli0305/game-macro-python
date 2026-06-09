# Progress

## Goal

Move built-in role profile skill and point seed data out of TypeScript factory code into a maintainable data asset.

## Done

- Added `src/assets/json/role-profile-seeds.json` as the source of truth for built-in role labels, descriptions, skills, points, pixel coordinates, and target colors.
- Refactored `src/utils/role-profile-templates.ts` so it only maps seed data into the existing `Profile`, `Skill`, and `Point` models.
- Enabled TypeScript JSON imports with `resolveJsonModule`.
- Added a regression test that built-in role options are derived from the seed asset.

## Files Changed

- `src/assets/json/role-profile-seeds.json`
- `src/utils/role-profile-templates.ts`
- `src/__tests__/role-profile-templates.test.ts`
- `tsconfig.json`

## Root Cause / Key Decision

The skill and point seeds were embedded in code, so adding or adjusting a role required editing factory logic. The new structure keeps executable behavior in TypeScript and moves role-specific data into JSON.

## Logs / Tests

- `pnpm.cmd exec vue-tsc --noEmit`
- `pnpm.cmd test -- src/__tests__/role-profile-templates.test.ts src/__tests__/cycle-presets.test.ts src/__tests__/profile-validation.test.ts`

## Risks

- Cycle presets are still code-backed in `src/utils/cycle-presets.ts`; adding a new role seed still needs a matching cycle preset until rotation data is also migrated.

## Next Step

Move cycle preset phase/lane definitions into a similar data asset once the current role profile seed format is stable.
