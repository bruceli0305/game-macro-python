# Condition Weaver Attunement Chain

## Sources
- SnowCrows: `https://snowcrows.com/builds/raids/elementalist/condition-weaver-pistol-dagger`
- DPS log JSON: `https://dps.report/getJson?permalink=26i4-20260418-202046_golem`

## Goal
Extract the attunement chain before implementing runtime rules. This document intentionally does not define UI pixel points or executor configuration. It only records what the rotation is trying to do.

## Weaver State Rule
For Weaver, pressing an attunement key changes:

```text
new primary = pressed attunement
new secondary = previous primary
```

Examples:

```text
Earth/Earth + Fire => Fire/Earth
Fire/Earth  + Fire => Fire/Fire
Fire/Fire   + Earth => Earth/Fire
Earth/Fire  + Earth => Earth/Earth
```

This is the rule the runtime must verify from the current frame. A phase name alone is not enough.

## SnowCrows Script Chain

### Preparation
- Stock `Earth Bullet`.
- `Fire Bullet` is optional.
- Fully attune to Earth before starting the encounter.

## Skill Key Legend

SnowCrows uses default skill-slot notation. The local profile may bind these slots to different physical keys, but the semantic slot is what matters.

| Script Slot | Meaning in This Build |
|---|---|
| `0` | `Weave Self` |
| `8` | `Signet of Fire` |
| `9` | `Signet of Earth` |
| Fire `1` | `Scorching Shot` |
| Fire `2` | `Raging Ricochet` |
| Fire `3` | `Searing Salvo` |
| Fire `4` | `Ring of Fire` |
| Fire `5` | `Fire Grab` |
| Earth `2` | `Shattering Stone` |
| Earth `3` | `Boulder Blast` |
| Earth `4` | `Earthquake` |
| Earth `5` | `Churning Earth` |
| Water `2` | `Frigid Flurry` |
| Air `1` | `Electric Exposure` |
| Air `2` | `Dazing Discharge` |
| Air `4` | `Ride the Lightning` |
| Fire/Earth `3` | `Molten Meteor` |
| Earth/Fire `3` | `Piercing Pebble` |
| Air/Earth `3` | `Enervating Earth` |
| Fire/Air `3` | `Purblinding Plasma` |
| Water/Earth `3` | `Echoing Erosion` |
| Fire/Water `3` | `Frostfire Flurry` |

Notes:
- `Sunspot`, `Earthen Blast`, and `Flame Expulsion` appear in the DPS log as instant/proc events and should not be treated as user-triggered macro skills.
- Some slot `3` dual skills can show multiple log names because the skill has chain/secondary effects. The runtime should still gate on the current attunement pair and slot readiness, not on a single hard-coded log name.

### Weave Self Rotation

| Step | Target Attunement | Press From Previous | Scripted Slots | Semantic Skills |
|---:|---|---|---|---|
| 1 | Earth/Earth | pre-start/manual Earth sync | `0`, `8`, `2`, `3` | `Weave Self`, `Signet of Fire`, `Shattering Stone`, `Boulder Blast` |
| 2 | Fire/Earth | Fire | `5`, `3` | `Churning Earth`, `Molten Meteor` |
| 3 | Fire/Fire | Fire | `3`, `2`, `4` | `Searing Salvo`, `Raging Ricochet`, `Ring of Fire` |
| 4 | Earth/Fire | Earth | `2`, `5` | `Shattering Stone`, `Fire Grab` |
| 5 | Earth/Earth | Earth | `2`, `3` | `Shattering Stone`, `Boulder Blast` |
| 6 | Air/Earth | Air | `8`, `2`, `3` | `Signet of Fire`, `Electric Exposure`, `Dazing Discharge` / `Enervating Earth` |
| 7 | Fire/Air | Fire | `2`, `3`, `4` | `Raging Ricochet`, `Purblinding Plasma`, `Ride the Lightning` |
| 8 | Fire/Fire | Fire | `3` | `Searing Salvo` |
| 9 | Earth/Fire | Earth | `2`, `3` | `Shattering Stone`, `Piercing Pebble` |
| 10 | Earth/Earth | Earth | `3` | `Boulder Blast` |
| 11 | Water/Earth | Water | `2`, `3`, `8`, `5` | `Frigid Flurry`, `Echoing Erosion`, `Signet of Fire`, `Churning Earth` / priority skill |
| 12 | Fire/Water | Fire | `3`, `2` | `Frostfire Flurry`, `Raging Ricochet` / `Scorching Shot` |

### Normal Loop

The stable loop is a four-state ring:

```text
Fire/Earth --Fire--> Fire/Fire --Earth--> Earth/Fire --Earth--> Earth/Earth --Fire--> Fire/Earth
```

Scripted loop steps:

| Step | Target Attunement | Press From Previous | Scripted Slots | Semantic Skills |
|---:|---|---|---|---|
| L1 | Fire/Fire | Fire | `3`, `2` | `Searing Salvo`, `Raging Ricochet` / `Scorching Shot` filler |
| L2 | Earth/Fire | Earth | `2`, `3` | `Shattering Stone`, `Piercing Pebble` |
| L3 | Earth/Earth | Earth | `3`, `2` | `Boulder Blast`, `Shattering Stone` |
| L4 | Fire/Earth | Fire | `2` | `Raging Ricochet` / `Scorching Shot` filler |

Priority note from SnowCrows:
- Use utility and off-hand priority skills when available: `Signet of Fire`, `Signet of Earth`, `Ring of Fire`, `Fire Grab`, `Earthquake`, and `Churning Earth`.
- Fill gaps with auto attacks.
- Pistol skill order is important because `Fire Bullet` and `Earth Bullet` affect damage.

## DPS Report Attunement Timeline

The DPS log confirms the same opener and four-state loop.

```text
 0.000s Earth/Earth
 0.722s Fire/Earth
 2.482s Fire/Fire
 4.562s Earth/Fire
 6.280s Earth/Earth
 9.798s Air/Earth
11.482s Fire/Air
13.239s Fire/Fire
14.882s Earth/Fire
16.560s Earth/Earth
18.522s Water/Earth
20.159s Fire/Water
23.480s Fire/Fire
26.722s Earth/Fire
30.082s Earth/Earth
33.318s Fire/Earth
36.679s Fire/Fire
39.923s Earth/Fire
43.241s Earth/Earth
46.481s Fire/Earth
49.761s Fire/Fire
53.040s Earth/Fire
56.281s Earth/Earth
59.599s Fire/Earth
62.920s Fire/Fire
66.240s Earth/Fire
69.518s Earth/Earth
72.841s Fire/Earth
74.480s Fire/Fire
76.157s Earth/Fire
77.880s Earth/Earth
81.397s Air/Earth
83.122s Fire/Air
84.840s Fire/Fire
86.564s Earth/Fire
88.203s Earth/Earth
90.078s Water/Earth
```

## DPS Report Phase Skill Breakdown

This section is the factual execution sample from the log. Times are relative to the attunement event that opened the segment.

### Weave Self / Opening Sample

| Phase | Time Window | Attunement | Observed Skills |
|---:|---|---|---|
| 1 | `0.000-0.722s` | Earth/Earth | `+0.122 Shattering Stone`, `+0.639 Boulder Blast` |
| 2 | `0.722-2.482s` | Fire/Earth | `+0.359 Churning Earth`, `+1.321 Molten Meteor` |
| 3 | `2.482-4.562s` | Fire/Fire | `+0.039 Signet of Earth`, `+0.557 Searing Salvo`, `+1.236 Raging Ricochet`, `+1.760 Ring of Fire`, `+1.919 Primordial Stance` |
| 4 | `4.562-6.280s` | Earth/Fire | `+0.156 Shattering Stone`, `+0.678 Fire Grab`, `+1.239 Piercing Pebble` |
| 5 | `6.280-9.798s` | Earth/Earth | `+0.037 Piercing Pebble`, `+0.206 Earthquake`, `+0.879 Piercing Pebble`, `+1.401 Piercing Pebble`, `+1.918 Piercing Pebble`, `+2.440 Piercing Pebble`, `+2.960 Shattering Stone`, `+3.482 Boulder Blast` |
| 6 | `9.798-11.482s` | Air/Earth | `+0.403 Signet of Fire`, `+0.920 Electric Exposure`, `+0.962 Dazing Discharge`, `+1.401 Enervating Earth` |
| 7 | `11.482-13.239s` | Fire/Air | `+0.281 Raging Ricochet`, `+0.801 Purblinding Plasma`, `+1.439 Ride the Lightning`, `+1.556 Scorching Shot` |
| 8 | `13.239-14.882s` | Fire/Fire | `+0.326 Searing Salvo`, `+1.001 Scorching Shot`, `+1.523 Ring of Fire` |
| 9 | `14.882-16.560s` | Earth/Fire | `+0.357 Signet of Earth`, `+0.516 Primordial Stance`, `+0.875 Shattering Stone`, `+1.396 Molten Meteor` |
| 10 | `16.560-18.522s` | Earth/Earth | `+0.201 Churning Earth`, `+1.161 Earthquake`, `+1.841 Boulder Blast` |
| 11 | `18.522-20.159s` | Water/Earth | `+0.318 Frigid Flurry`, `+1.316 Echoing Erosion` |
| 12 | `20.159-23.480s` | Fire/Water | `+0.158 Scorching Shot`, `+0.243 Signet of Fire`, `+0.760 Frostfire Flurry`, `+1.401 Raging Ricochet`, `+1.923 Scorching Shot`, `+2.439 Scorching Shot`, `+2.962 Scorching Shot` |

### Stable Loop Sample

The first clean repeated loop in the log begins after the opening `Fire/Water` segment and repeatedly follows `Fire/Fire -> Earth/Fire -> Earth/Earth -> Fire/Earth`.

| Phase | Time Window | Attunement | Observed Skills |
|---:|---|---|---|
| L1 | `23.480-26.722s` | Fire/Fire | `+0.117 Fire Grab`, `+0.680 Searing Salvo`, `+1.361 Scorching Shot`, `+1.882 Ring of Fire`, `+2.361 Scorching Shot`, `+2.879 Raging Ricochet` |
| L2 | `26.722-30.082s` | Earth/Fire | `+0.155 Shattering Stone`, `+0.676 Piercing Pebble`, `+1.199 Signet of Earth`, `+1.716 Molten Meteor`, `+2.200 Piercing Pebble`, `+2.718 Piercing Pebble`, `+3.239 Piercing Pebble` |
| L3 | `30.082-33.318s` | Earth/Earth | `+0.398 Piercing Pebble`, `+0.476 Signet of Fire`, `+0.997 Churning Earth`, `+1.959 Earthquake`, `+2.638 Boulder Blast`, `+3.075 Shattering Stone` |
| L4 | `33.318-36.679s` | Fire/Earth | `+0.360 Raging Ricochet`, `+0.880 Scorching Shot`, `+1.402 Scorching Shot`, `+1.923 Scorching Shot`, `+2.439 Scorching Shot`, `+2.960 Scorching Shot` |
| L1 | `36.679-39.923s` | Fire/Fire | `+0.121 Scorching Shot`, `+0.642 Ring of Fire`, `+1.123 Fire Grab`, `+1.681 Searing Salvo`, `+2.360 Raging Ricochet`, `+2.881 Scorching Shot` |
| L2 | `39.923-43.241s` | Earth/Fire | `+0.159 Piercing Pebble`, `+0.678 Signet of Earth`, `+1.195 Signet of Fire`, `+1.476 Primordial Stance`, `+1.717 Shattering Stone`, `+2.237 Molten Meteor`, `+2.718 Piercing Pebble`, `+3.235 Piercing Pebble` |
| L3 | `43.241-46.481s` | Earth/Earth | `+0.438 Earthquake`, `+1.117 Boulder Blast`, `+1.560 Piercing Pebble`, `+1.760 Churning Earth`, `+2.717 Piercing Pebble`, `+2.876 Shattering Stone` |
| L4 | `46.481-49.761s` | Fire/Earth | `+0.160 Raging Ricochet`, `+0.677 Scorching Shot`, `+1.196 Scorching Shot`, `+1.717 Scorching Shot`, `+2.239 Scorching Shot`, `+2.759 Scorching Shot` |

## Phase Implementation Direction

Each phase should be represented as:

```text
target_attunement
required_transition_key
mandatory_skills
priority_skills
filler_skills
exit_condition
```

Example for a stable-loop phase:

```text
target_attunement = Earth/Fire
required_transition_key = Earth
mandatory_skills = [Shattering Stone, Piercing Pebble]
priority_skills = [Signet of Earth, Molten Meteor, Primordial Stance if ready]
filler_skills = [Piercing Pebble / auto chain]
exit_condition = next attunement key is available and mandatory skills are no longer ready
```

The implementation should not assume every observed log skill must fire every cycle. The log shows priority insertions and filler variance. The hard requirements are:
- The target attunement is confirmed.
- The phase-specific mandatory weapon skills are evaluated first.
- Priority utilities/off-hand skills can interrupt when ready.
- Filler skills only run when no mandatory or priority skill is ready.

## Weave Self / Opening Executable Phase Rules

These rules describe the opening chain before the rotation settles into the normal loop. They should be implemented after the stable loop state machine is proven, because the opening has more one-off transitions and more cooldown-dependent priority inserts.

Important log note:
- SnowCrows labels this section as `Weave Self Rotation`, but the DPS sample does not show a `Weave Self` cast at `0s`; the visible `Weave Self` cast appears later around `71.719s`.
- The first visible opening skill in the DPS log is `Signet of Fire` at `-0.401s`, before the first attunement event.
- Therefore `Weave Self` should be treated as a strategy trigger/entry condition, not as a mandatory first frame action unless the runtime confirms it is ready and intended.

### P1: Earth/Earth Entry

```text
target_attunement = Earth/Earth
required_transition_key = pre-start Earth sync or Earth
expected_transition = Earth/Fire + Earth => Earth/Earth
```

Mandatory skills:
- `Shattering Stone`
- `Boulder Blast`

Priority skills:
- `Weave Self` if this is the selected burst entry and the skill is ready.
- `Signet of Fire` if available and configured as a pre-burst priority.

Filler:
- none; this is a short setup segment.

Exit condition:
- Target state is `Earth/Earth`.
- `Shattering Stone` and `Boulder Blast` have fired or are not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Earth`.

Observed sample:

```text
0.000-0.722 Earth/Earth:
Shattering Stone -> Boulder Blast
```

### P2: Fire/Earth

```text
target_attunement = Fire/Earth
required_transition_key = Fire
expected_transition = Earth/Earth + Fire => Fire/Earth
```

Mandatory skills:
- `Churning Earth`
- `Molten Meteor`

Priority skills:
- none in the observed sample.

Filler:
- none; this segment is short and skill-specific.

Exit condition:
- Target state is `Fire/Earth`.
- `Churning Earth` and `Molten Meteor` have fired or are not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Fire`.

Observed sample:

```text
0.722-2.482 Fire/Earth:
Churning Earth -> Molten Meteor
```

### P3: Fire/Fire

```text
target_attunement = Fire/Fire
required_transition_key = Fire
expected_transition = Fire/Earth + Fire => Fire/Fire
```

Mandatory skills:
- `Searing Salvo`
- `Raging Ricochet`
- `Ring of Fire`

Priority skills:
- `Signet of Earth`
- `Primordial Stance`

Filler:
- Fire auto / `Scorching Shot` only if the mandatory and priority skills are not ready.

Exit condition:
- Target state is `Fire/Fire`.
- Main Fire skills have fired or are no longer ready.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Fire`.

Observed sample:

```text
2.482-4.562 Fire/Fire:
Signet of Earth -> Searing Salvo -> Raging Ricochet -> Ring of Fire -> Primordial Stance
```

### P4: Earth/Fire

```text
target_attunement = Earth/Fire
required_transition_key = Earth
expected_transition = Fire/Fire + Earth => Earth/Fire
```

Mandatory skills:
- `Shattering Stone`
- `Fire Grab`

Priority skills:
- none in the observed sample.

Filler:
- `Piercing Pebble`

Exit condition:
- Target state is `Earth/Fire`.
- `Shattering Stone` and `Fire Grab` have fired or are not ready.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Earth`.

Observed sample:

```text
4.562-6.280 Earth/Fire:
Shattering Stone -> Fire Grab -> Piercing Pebble
```

### P5: Earth/Earth Extended Fill

```text
target_attunement = Earth/Earth
required_transition_key = Earth
expected_transition = Earth/Fire + Earth => Earth/Earth
```

Mandatory skills:
- `Earthquake`
- `Shattering Stone`
- `Boulder Blast`

Priority skills:
- none in the observed sample.

Filler:
- `Piercing Pebble`

Exit condition:
- Target state is `Earth/Earth`.
- `Earthquake`, `Shattering Stone`, and `Boulder Blast` have fired or are not ready.
- `Air Attunement` is available.
- Then press Air to enter `Air/Earth`.

Observed sample:

```text
6.280-9.798 Earth/Earth:
Piercing Pebble -> Earthquake -> Piercing Pebble... -> Shattering Stone -> Boulder Blast
```

### P6: Air/Earth

```text
target_attunement = Air/Earth
required_transition_key = Air
expected_transition = Earth/Earth + Air => Air/Earth
```

Mandatory skills:
- `Electric Exposure`
- `Dazing Discharge`
- `Enervating Earth`

Priority skills:
- `Signet of Fire`

Filler:
- none; this is a short transition burst.

Exit condition:
- Target state is `Air/Earth`.
- Air/Earth skills have fired or are not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Air`.

Observed sample:

```text
9.798-11.482 Air/Earth:
Signet of Fire -> Electric Exposure -> Dazing Discharge -> Enervating Earth
```

### P7: Fire/Air

```text
target_attunement = Fire/Air
required_transition_key = Fire
expected_transition = Air/Earth + Fire => Fire/Air
```

Mandatory skills:
- `Raging Ricochet`
- `Purblinding Plasma`
- `Ride the Lightning`

Priority skills:
- none in the observed sample.

Filler:
- `Scorching Shot`

Exit condition:
- Target state is `Fire/Air`.
- Mandatory Fire/Air skills have fired or are not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Fire`.

Observed sample:

```text
11.482-13.239 Fire/Air:
Raging Ricochet -> Purblinding Plasma -> Ride the Lightning -> Scorching Shot
```

### P8: Fire/Fire Short

```text
target_attunement = Fire/Fire
required_transition_key = Fire
expected_transition = Fire/Air + Fire => Fire/Fire
```

Mandatory skills:
- `Searing Salvo`
- `Ring of Fire`

Priority skills:
- none in the observed sample.

Filler:
- `Scorching Shot`

Exit condition:
- Target state is `Fire/Fire`.
- Fire mandatory skills have fired or are not ready.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Fire`.

Observed sample:

```text
13.239-14.882 Fire/Fire:
Searing Salvo -> Scorching Shot -> Ring of Fire
```

### P9: Earth/Fire Utility Insert

```text
target_attunement = Earth/Fire
required_transition_key = Earth
expected_transition = Fire/Fire + Earth => Earth/Fire
```

Mandatory skills:
- `Shattering Stone`
- `Molten Meteor`

Priority skills:
- `Signet of Earth`
- `Primordial Stance`

Filler:
- none in the observed sample.

Exit condition:
- Target state is `Earth/Fire`.
- Mandatory dual/Earth skills have fired or are not ready.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Earth`.

Observed sample:

```text
14.882-16.560 Earth/Fire:
Signet of Earth -> Primordial Stance -> Shattering Stone -> Molten Meteor
```

### P10: Earth/Earth Short

```text
target_attunement = Earth/Earth
required_transition_key = Earth
expected_transition = Earth/Fire + Earth => Earth/Earth
```

Mandatory skills:
- `Boulder Blast`

Priority skills:
- `Churning Earth`
- `Earthquake`

Filler:
- none in the observed sample.

Exit condition:
- Target state is `Earth/Earth`.
- Earth priority skills have fired or are not ready.
- `Water Attunement` is available.
- Then press Water to enter `Water/Earth`.

Observed sample:

```text
16.560-18.522 Earth/Earth:
Churning Earth -> Earthquake -> Boulder Blast
```

### P11: Water/Earth

```text
target_attunement = Water/Earth
required_transition_key = Water
expected_transition = Earth/Earth + Water => Water/Earth
```

Mandatory skills:
- `Frigid Flurry`
- `Echoing Erosion`

Priority skills:
- none in the observed sample. SnowCrows script also lists `8` and `5`, but they do not appear in this exact log segment.

Filler:
- none; this is a short transition segment.

Exit condition:
- Target state is `Water/Earth`.
- Water/Earth skills have fired or are not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Water`.

Observed sample:

```text
18.522-20.159 Water/Earth:
Frigid Flurry -> Echoing Erosion
```

### P12: Fire/Water

```text
target_attunement = Fire/Water
required_transition_key = Fire
expected_transition = Water/Earth + Fire => Fire/Water
```

Mandatory skills:
- `Frostfire Flurry`
- Fire `2` equivalent if ready.

Priority skills:
- `Signet of Fire`

Filler:
- `Scorching Shot`
- `Raging Ricochet`

Exit condition:
- Target state is `Fire/Water`.
- `Frostfire Flurry` has fired or is not ready.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Fire` and begin the stable loop.

Observed sample:

```text
20.159-23.480 Fire/Water:
Scorching Shot -> Signet of Fire -> Frostfire Flurry -> Raging Ricochet -> Scorching Shot...
```

## Weave Self Opening State Machine Summary

```text
P1  Earth/Earth
    mandatory: Shattering Stone, Boulder Blast
    priority: Weave Self trigger, Signet of Fire
    exit: press Fire

P2  Fire/Earth
    mandatory: Churning Earth, Molten Meteor
    exit: press Fire

P3  Fire/Fire
    mandatory: Searing Salvo, Raging Ricochet, Ring of Fire
    priority: Signet of Earth, Primordial Stance
    exit: press Earth

P4  Earth/Fire
    mandatory: Shattering Stone, Fire Grab
    filler: Piercing Pebble
    exit: press Earth

P5  Earth/Earth
    mandatory: Earthquake, Shattering Stone, Boulder Blast
    filler: Piercing Pebble
    exit: press Air

P6  Air/Earth
    mandatory: Electric Exposure, Dazing Discharge, Enervating Earth
    priority: Signet of Fire
    exit: press Fire

P7  Fire/Air
    mandatory: Raging Ricochet, Purblinding Plasma, Ride the Lightning
    filler: Scorching Shot
    exit: press Fire

P8  Fire/Fire
    mandatory: Searing Salvo, Ring of Fire
    filler: Scorching Shot
    exit: press Earth

P9  Earth/Fire
    mandatory: Shattering Stone, Molten Meteor
    priority: Signet of Earth, Primordial Stance
    exit: press Earth

P10 Earth/Earth
    mandatory: Boulder Blast
    priority: Churning Earth, Earthquake
    exit: press Water

P11 Water/Earth
    mandatory: Frigid Flurry, Echoing Erosion
    exit: press Fire

P12 Fire/Water
    mandatory: Frostfire Flurry, Fire 2
    priority: Signet of Fire
    filler: Scorching Shot
    exit: press Fire into stable loop
```

## Stable Loop Executable Phase Rules

These rules are the first practical target for implementation. They describe how the state machine should behave once the opener has settled into the normal loop.

### L1: Fire/Fire

```text
target_attunement = Fire/Fire
required_transition_key = Fire
expected_transition = Fire/Earth + Fire => Fire/Fire
```

Mandatory skills:
- `Searing Salvo`
- `Raging Ricochet` or current Fire `2` equivalent if ready

Priority skills:
- `Fire Grab`
- `Ring of Fire`
- `Signet of Fire` if available and not needed more urgently by the next phase
- `Signet of Earth` only if ready and it does not delay the attunement transition

Filler:
- `Scorching Shot`
- auto chain

Exit condition:
- Target state is still `Fire/Fire`.
- Mandatory Fire skills are not ready or have just fired.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Fire`.

Observed loop samples:

```text
23.480-26.722 Fire/Fire:
Fire Grab -> Searing Salvo -> Scorching Shot -> Ring of Fire -> Scorching Shot -> Raging Ricochet

36.679-39.923 Fire/Fire:
Scorching Shot -> Ring of Fire -> Fire Grab -> Searing Salvo -> Raging Ricochet -> Scorching Shot

49.761-53.040 Fire/Fire:
Scorching Shot -> Ring of Fire -> Searing Salvo -> Signet of Fire -> Fire Grab -> Raging Ricochet
```

Implementation note:
- Do not require exact order between `Fire Grab`, `Ring of Fire`, and `Searing Salvo`; they are priority decisions based on current readiness.
- Do require the phase to stay in `Fire/Fire` before firing Fire-only skills.

### L2: Earth/Fire

```text
target_attunement = Earth/Fire
required_transition_key = Earth
expected_transition = Fire/Fire + Earth => Earth/Fire
```

Mandatory skills:
- `Shattering Stone`
- `Molten Meteor`

Priority skills:
- `Signet of Earth`
- `Primordial Stance`
- `Signet of Fire` if available

Filler:
- `Piercing Pebble`
- auto chain

Exit condition:
- Target state is still `Earth/Fire`.
- `Shattering Stone` and `Molten Meteor` are not ready or have just fired.
- `Earth Attunement` is available.
- Then press Earth to enter `Earth/Earth`.

Observed loop samples:

```text
26.722-30.082 Earth/Fire:
Shattering Stone -> Piercing Pebble -> Signet of Earth -> Molten Meteor -> Piercing Pebble...

39.923-43.241 Earth/Fire:
Piercing Pebble -> Signet of Earth -> Signet of Fire -> Primordial Stance -> Shattering Stone -> Molten Meteor -> Piercing Pebble...

53.040-56.281 Earth/Fire:
Piercing Pebble -> Signet of Earth -> Shattering Stone -> Molten Meteor -> Primordial Stance -> Piercing Pebble...
```

Implementation note:
- `Piercing Pebble` appears frequently and should be treated as filler unless a specific bullet/chain condition makes it mandatory.
- `Molten Meteor` is the important dual skill for this phase and should be checked before filler.

### L3: Earth/Earth

```text
target_attunement = Earth/Earth
required_transition_key = Earth
expected_transition = Earth/Fire + Earth => Earth/Earth
```

Mandatory skills:
- `Boulder Blast`
- `Shattering Stone`

Priority skills:
- `Earthquake`
- `Churning Earth`
- `Signet of Fire`
- `Weave Self` when available and the rotation should re-enter the Weave Self chain

Filler:
- `Piercing Pebble`
- auto chain

Exit condition:
- Target state is still `Earth/Earth`.
- `Boulder Blast` and `Shattering Stone` are not ready or have just fired.
- `Fire Attunement` is available.
- If `Weave Self` is ready and strategy says to restart burst, transition to the opening chain instead of the normal L4 path.
- Otherwise press Fire to enter `Fire/Earth`.

Observed loop samples:

```text
30.082-33.318 Earth/Earth:
Piercing Pebble -> Signet of Fire -> Churning Earth -> Earthquake -> Boulder Blast -> Shattering Stone

43.241-46.481 Earth/Earth:
Earthquake -> Boulder Blast -> Piercing Pebble -> Churning Earth -> Piercing Pebble -> Shattering Stone

69.518-72.841 Earth/Earth:
Piercing Pebble -> Earthquake -> Boulder Blast -> Shattering Stone -> Weave Self -> Signet of Fire
```

Implementation note:
- `Earthquake` and `Churning Earth` are high value but cooldown-driven; do not block the loop waiting for them if they are not ready.
- `Weave Self` should be modeled as a strategy transition trigger, not a normal filler skill.

### L4: Fire/Earth

```text
target_attunement = Fire/Earth
required_transition_key = Fire
expected_transition = Earth/Earth + Fire => Fire/Earth
```

Mandatory skills:
- Fire `2` equivalent: `Raging Ricochet` when available.

Priority skills:
- `Churning Earth` if it carried over and is ready immediately after the transition.
- `Signet of Fire` if available.

Filler:
- `Scorching Shot`
- auto chain

Exit condition:
- Target state is still `Fire/Earth`.
- Fire `2` is not ready or has just fired.
- `Fire Attunement` is available.
- Then press Fire to enter `Fire/Fire`.

Observed loop samples:

```text
33.318-36.679 Fire/Earth:
Raging Ricochet -> Scorching Shot...

46.481-49.761 Fire/Earth:
Raging Ricochet -> Scorching Shot...

59.599-62.920 Fire/Earth:
Raging Ricochet -> Scorching Shot... -> Signet of Fire -> Scorching Shot...
```

Implementation note:
- This phase is mostly a bridge back to full Fire. It should not overstay if `Fire Attunement` is available and Fire `2` has been consumed or is not ready.
- The DPS log shows long `Scorching Shot` filler chains here; those should be optional filler, not a required fixed count.

## Stable Loop State Machine Summary

```text
L1 Fire/Fire
  mandatory: Searing Salvo, Fire 2
  priority: Fire Grab, Ring of Fire
  filler: Scorching Shot
  exit: press Earth

L2 Earth/Fire
  mandatory: Shattering Stone, Molten Meteor
  priority: Signet of Earth, Primordial Stance
  filler: Piercing Pebble
  exit: press Earth

L3 Earth/Earth
  mandatory: Boulder Blast, Shattering Stone
  priority: Earthquake, Churning Earth, Weave Self trigger
  filler: Piercing Pebble
  exit: press Fire

L4 Fire/Earth
  mandatory: Fire 2
  priority: Signet of Fire
  filler: Scorching Shot
  exit: press Fire
```

The next implementation should start with these four rules before attempting the full Weave Self opener.

## Runtime Implications

The macro should not execute this as a fixed list of phases. It should use a state machine:

1. Read current `primary/secondary` from frame.
2. Pick the next target attunement segment from the chain.
3. If current state is not target state, compute the attunement key to press.
4. Press the attunement key only if that key is available.
5. Re-read the frame and confirm the expected state transition.
6. Only then evaluate skills that belong to that attunement segment.

## Minimal State Machine Targets

### Opening chain

```text
Earth/Earth
Fire/Earth
Fire/Fire
Earth/Fire
Earth/Earth
Air/Earth
Fire/Air
Fire/Fire
Earth/Fire
Earth/Earth
Water/Earth
Fire/Water
Fire/Fire
```

### Stable loop

```text
Fire/Fire
Earth/Fire
Earth/Earth
Fire/Earth
```

After `Fire/Earth`, press Fire to return to `Fire/Fire`.

## Key Decision
The current executor configuration should be treated as a seed only. The practical implementation must be driven by the observed attunement state and confirmed transitions, not by assuming the next phase can always run.

## Executable Preset Design

The current built-in preset maps the document into the existing `CyclePhase + AssistLane` executor without adding new engine semantics.

Main phase responsibilities:
- Opening phases P1-P12 confirm the target attunement before firing phase-owned mandatory skills.
- P6 uses `Electric Exposure -> Dazing Discharge -> Enervating Earth`.
- P7 uses `Raging Ricochet -> Purblinding Plasma -> Ride the Lightning`.
- P10 now keeps `Earthquake` and `Churning Earth` as Earth/Earth priority inserts before `Boulder Blast`.
- P12 now evaluates `Frostfire Flurry`, `Signet of Fire`, `Raging Ricochet`, and `Scorching Shot` before the next `Fire` press transitions into stable `Fire/Fire`.
- Stable L3 (`Earth/Earth`) conditionally jumps back to `Weave Self - Earth opener` when `Weave Self` is ready; otherwise it continues to L4.

Phase completion semantics:
- If a phase contains any `mandatory` slot, only `mandatory` slots decide `any_fired`, `none_ready`, and `all_fired` completion.
- If a phase contains no `mandatory` slot, non-`filler` slots decide completion.
- If a phase contains only `filler` slots, all slots decide completion.
- `priority` and `filler` slots can still execute by priority order, but they do not block phase exit when `mandatory` slots exist.

Assist lane responsibilities:
- Utility skills remain in `weaver_priority_skills` so they can interrupt while the main slot waits for completion.
- Off-hand Fire/Earth skills remain in `weaver_dagger_priority` so they do not block phase exit.
- Fillers remain in `weaver_auto_attack_fill`; `Scorching Shot` covers Fire states and `Piercing Pebble` covers Earth states.

Known limitation:
- The executor now understands `mandatory / priority / filler` for phase completion, and the phase editor groups skills by those roles. The remaining UX gap is drag/drop or bulk reordering across role groups; priority order is still edited through each skill slot's priority value.
