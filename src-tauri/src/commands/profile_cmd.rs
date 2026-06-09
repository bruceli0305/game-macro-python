//! Profile configuration CRUD commands.
use crate::ast::compiler::compile_expr_json;
use crate::error::{AppError, AppResult, CommandResult};
use crate::models::cycle::{
    AssistInterruptPolicy, CycleConfig, ObserverActionSlot, PhaseFallbackTransition, RuntimeAction,
    SkillSlot,
};
use crate::models::profile::Profile;
use crate::models::skill::{PixelSpec, SampleConfig};
use crate::store::profile_store::ProfileStore;
use serde::Serialize;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct ProfileInfo {
    pub name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ActiveProfileInfo {
    pub name: String,
}

fn get_store() -> AppResult<ProfileStore> {
    let dir = app_data_dir()?;
    Ok(ProfileStore::new(dir))
}

#[tauri::command]
pub fn profile_list() -> CommandResult<Vec<ProfileInfo>> {
    let store = get_store()?;
    let names = store.list()?;
    Ok(names.into_iter().map(|name| ProfileInfo { name }).collect())
}

#[tauri::command]
pub fn profile_get_active() -> CommandResult<ActiveProfileInfo> {
    let store = get_store()?;
    Ok(ActiveProfileInfo {
        name: store.active_profile_name()?,
    })
}

#[tauri::command]
pub fn profile_set_active(name: String) -> CommandResult<()> {
    let store = get_store()?;
    Ok(store.set_active_profile_name(&name)?)
}

#[tauri::command]
pub fn profile_load(name: String) -> CommandResult<String> {
    let store = get_store()?;
    let profile = if name == "default" {
        store.load_or_create_default(&name)?
    } else {
        store.load(&name)?
    };
    Ok(serde_json::to_string_pretty(&profile).map_err(AppError::from)?)
}

#[tauri::command]
pub fn profile_save(name: String, content: String) -> CommandResult<()> {
    let store = get_store()?;
    let profile: Profile = serde_json::from_str(&content).map_err(AppError::from)?;
    validate_profile_references(&profile)?;
    Ok(store.save(&name, &profile)?)
}

fn validate_profile_references(profile: &Profile) -> AppResult<()> {
    validate_base_config(profile)?;

    let pick_hotkey = profile.base.pick.confirm_hotkey.trim().to_uppercase();
    let toggle_hotkey = profile.base.exec.toggle_hotkey.trim().to_uppercase();
    if !pick_hotkey.is_empty() && !toggle_hotkey.is_empty() && pick_hotkey == toggle_hotkey {
        return Err(AppError::Config(format!(
            "pick confirm hotkey and engine toggle hotkey must differ: {toggle_hotkey}"
        )));
    }

    let mut skill_ids = HashSet::new();
    for skill in &profile.skills.skills {
        let skill_id = skill.id.trim();
        if skill_id.is_empty() {
            return Err(AppError::Config("skills contains an empty skill id".into()));
        }
        if skill.name.trim().is_empty() {
            return Err(AppError::Config(format!(
                "skill '{skill_id}' has an empty name"
            )));
        }
        if !skill_ids.insert(skill_id) {
            return Err(AppError::Config(format!("duplicate skill id '{skill_id}'")));
        }
        validate_pixel_spec(&format!("skills.{skill_id}.pixel"), &skill.pixel)?;

        let mut ammo_charges = HashSet::new();
        for (stage_index, stage) in skill.ammo_stages.iter().enumerate() {
            if !ammo_charges.insert(stage.charges_left) {
                return Err(AppError::Config(format!(
                    "skill '{skill_id}' has duplicate ammo stage charges_left {}",
                    stage.charges_left
                )));
            }
            validate_pixel_spec(
                &format!("skills.{skill_id}.ammo_stages[{stage_index}].pixel"),
                &stage.pixel,
            )?;
        }
    }

    let mut point_ids = HashSet::new();
    for point in &profile.points.points {
        let point_id = point.id.trim();
        if point_id.is_empty() {
            return Err(AppError::Config("points contains an empty point id".into()));
        }
        if point.name.trim().is_empty() {
            return Err(AppError::Config(format!(
                "point '{point_id}' has an empty name"
            )));
        }
        validate_sample_config(&format!("points.{point_id}.sample"), &point.sample)?;
        if point.monitor.trim().is_empty() {
            return Err(AppError::Config(format!(
                "point '{point_id}' has an empty monitor"
            )));
        }
        if !point_ids.insert(point_id) {
            return Err(AppError::Config(format!("duplicate point id '{point_id}'")));
        }
    }

    let cast_bar_point_id = profile.base.cast_bar.point_id.trim();
    if profile.base.cast_bar.mode == "pixel" {
        if cast_bar_point_id.is_empty() {
            return Err(AppError::Config(
                "base.cast_bar.point_id is required when cast bar mode is pixel".into(),
            ));
        }
        if !point_ids.contains(cast_bar_point_id) {
            return Err(AppError::Config(format!(
                "base.cast_bar.point_id references missing point '{cast_bar_point_id}'"
            )));
        }
    } else if !cast_bar_point_id.is_empty() && !point_ids.contains(cast_bar_point_id) {
        return Err(AppError::Config(format!(
            "base.cast_bar.point_id references missing point '{cast_bar_point_id}'"
        )));
    }

    for (rotation_index, rotation) in profile.rotations.iter().enumerate() {
        validate_rotation_config(rotation_index, rotation.poll_interval_ms)?;
        let state_refs = validate_state_schema(rotation_index, rotation)?;
        let phase_names = validate_phase_names(rotation_index, rotation)?;
        for (phase_index, phase) in rotation.phases.iter().enumerate() {
            validate_runtime_actions(
                &format!("rotations[{rotation_index}].phases[{phase_index}].entry_actions"),
                &phase.entry_actions,
                &state_refs,
            )?;
            validate_phase_transitions(
                rotation_index,
                phase_index,
                phase,
                &phase_names,
                &skill_ids,
                &point_ids,
                &state_refs,
            )?;
            for (slot_index, slot) in phase.skills.iter().enumerate() {
                validate_skill_slot_refs(
                    &format!(
                        "rotations[{rotation_index}].phases[{phase_index}].skills[{slot_index}]"
                    ),
                    slot,
                    &skill_ids,
                    &point_ids,
                    &state_refs,
                )?;
            }
        }
        validate_assist_lanes(
            rotation_index,
            rotation,
            &skill_ids,
            &point_ids,
            &state_refs,
        )?;
        validate_observer_lanes(
            rotation_index,
            rotation,
            &skill_ids,
            &point_ids,
            &state_refs,
        )?;
    }

    Ok(())
}

fn validate_base_config(profile: &Profile) -> AppResult<()> {
    let base = &profile.base;
    if base.capture.monitor_policy.trim().is_empty() {
        return Err(AppError::Config(
            "base.capture.monitor_policy must not be empty".into(),
        ));
    }

    if base.pick.confirm_hotkey.trim().is_empty() {
        return Err(AppError::Config(
            "base.pick.confirm_hotkey must not be empty".into(),
        ));
    }
    if base.pick.mouse_avoid_offset_y < -1000 || base.pick.mouse_avoid_offset_y > 1000 {
        return Err(AppError::Config(
            "base.pick.mouse_avoid_offset_y must be between -1000 and 1000".into(),
        ));
    }
    if base.pick.mouse_avoid_settle_ms > 5000 {
        return Err(AppError::Config(
            "base.pick.mouse_avoid_settle_ms must be between 0 and 5000".into(),
        ));
    }

    match base.cast_bar.mode.trim() {
        "timer" | "pixel" | "roi" => {}
        mode => {
            return Err(AppError::Config(format!(
                "base.cast_bar.mode must be timer, pixel, or roi, got '{mode}'"
            )));
        }
    }
    if base.cast_bar.poll_interval_ms == 0 || base.cast_bar.poll_interval_ms > 10000 {
        return Err(AppError::Config(
            "base.cast_bar.poll_interval_ms must be between 1 and 10000".into(),
        ));
    }
    if !base.cast_bar.max_wait_factor.is_finite()
        || base.cast_bar.max_wait_factor < 0.1
        || base.cast_bar.max_wait_factor > 10.0
    {
        return Err(AppError::Config(
            "base.cast_bar.max_wait_factor must be between 0.1 and 10.0".into(),
        ));
    }
    validate_cast_bar_roi_config(base.cast_bar.mode.trim(), &base.cast_bar.roi)?;

    if base.exec.toggle_hotkey.trim().is_empty() {
        return Err(AppError::Config(
            "base.exec.toggle_hotkey must not be empty".into(),
        ));
    }
    if base.exec.default_skill_gap_ms > 10000 {
        return Err(AppError::Config(
            "base.exec.default_skill_gap_ms must be between 0 and 10000".into(),
        ));
    }
    if base.exec.poll_not_ready_ms == 0 || base.exec.poll_not_ready_ms > 10000 {
        return Err(AppError::Config(
            "base.exec.poll_not_ready_ms must be between 1 and 10000".into(),
        ));
    }
    if base.exec.max_retries > 20 {
        return Err(AppError::Config(
            "base.exec.max_retries must be between 0 and 20".into(),
        ));
    }
    if base.exec.retry_gap_ms > 10000 {
        return Err(AppError::Config(
            "base.exec.retry_gap_ms must be between 0 and 10000".into(),
        ));
    }

    Ok(())
}

fn validate_cast_bar_roi_config(
    cast_bar_mode: &str,
    roi: &crate::models::base::CastBarRoiConfig,
) -> AppResult<()> {
    if roi.enabled || cast_bar_mode == "roi" {
        if roi.monitor.trim().is_empty() {
            return Err(AppError::Config(
                "base.cast_bar.roi.monitor must not be empty".into(),
            ));
        }
        if roi.width == 0 || roi.width > 2000 {
            return Err(AppError::Config(
                "base.cast_bar.roi.width must be between 1 and 2000".into(),
            ));
        }
        if roi.height == 0 || roi.height > 500 {
            return Err(AppError::Config(
                "base.cast_bar.roi.height must be between 1 and 500".into(),
            ));
        }
    }
    if !roi.min_changed_ratio.is_finite()
        || roi.min_changed_ratio < 0.0
        || roi.min_changed_ratio > 1.0
    {
        return Err(AppError::Config(
            "base.cast_bar.roi.min_changed_ratio must be between 0 and 1".into(),
        ));
    }
    if !roi.min_border_match_ratio.is_finite()
        || roi.min_border_match_ratio < 0.0
        || roi.min_border_match_ratio > 1.0
    {
        return Err(AppError::Config(
            "base.cast_bar.roi.min_border_match_ratio must be between 0 and 1".into(),
        ));
    }
    if roi.confirm_frames == 0 || roi.confirm_frames > 10 {
        return Err(AppError::Config(
            "base.cast_bar.roi.confirm_frames must be between 1 and 10".into(),
        ));
    }
    Ok(())
}

fn validate_rotation_config(rotation_index: usize, poll_interval_ms: u32) -> AppResult<()> {
    if poll_interval_ms == 0 || poll_interval_ms > 10000 {
        return Err(AppError::Config(format!(
            "rotations[{rotation_index}].poll_interval_ms must be between 1 and 10000"
        )));
    }
    Ok(())
}

fn validate_phase_names(
    rotation_index: usize,
    rotation: &CycleConfig,
) -> AppResult<HashSet<String>> {
    let mut names = HashSet::new();
    for (phase_index, phase) in rotation.phases.iter().enumerate() {
        let name = phase.name.trim();
        if name.is_empty() {
            continue;
        }
        if !names.insert(name.to_string()) {
            return Err(AppError::Config(format!(
                "rotations[{rotation_index}].phases[{phase_index}].name duplicates phase '{name}'"
            )));
        }
    }
    Ok(names)
}

fn validate_phase_transitions(
    rotation_index: usize,
    phase_index: usize,
    phase: &crate::models::cycle::CyclePhase,
    phase_names: &HashSet<String>,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let phase_path = format!("rotations[{rotation_index}].phases[{phase_index}]");
    for (rule_index, rule) in phase.transition_rules.iter().enumerate() {
        let rule_path = format!("{phase_path}.transition_rules[{rule_index}]");
        if rule.target_phase.trim().is_empty() {
            return Err(AppError::Config(format!(
                "{rule_path}.target_phase must not be empty"
            )));
        }
        if !phase_names.contains(rule.target_phase.trim()) {
            return Err(AppError::Config(format!(
                "{rule_path}.target_phase references missing phase '{}'",
                rule.target_phase
            )));
        }
        validate_expr_refs(
            &rule.condition_expr,
            &format!("{rule_path}.condition_expr"),
            skill_ids,
            point_ids,
            state_refs,
        )?;
        if rule.condition_expr.is_none() {
            return Err(AppError::Config(format!(
                "{rule_path}.condition_expr must not be empty"
            )));
        }
    }

    if let Some(PhaseFallbackTransition::Phase { target_phase }) = &phase.fallback_transition {
        if target_phase.trim().is_empty() {
            return Err(AppError::Config(format!(
                "{phase_path}.fallback_transition.target_phase must not be empty"
            )));
        }
        if !phase_names.contains(target_phase.trim()) {
            return Err(AppError::Config(format!(
                "{phase_path}.fallback_transition.target_phase references missing phase '{target_phase}'"
            )));
        }
    }
    Ok(())
}

fn validate_skill_slot_refs(
    path: &str,
    slot: &SkillSlot,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let skill_id = slot.skill_id.trim();
    if !skill_id.is_empty() && !skill_ids.contains(skill_id) {
        return Err(AppError::Config(format!(
            "{path}.skill_id references missing skill '{skill_id}'"
        )));
    }

    validate_expr_refs(
        &slot.condition_expr,
        &format!("{path}.condition_expr"),
        skill_ids,
        point_ids,
        state_refs,
    )?;
    validate_expr_refs(
        &slot.start_expr,
        &format!("{path}.start_expr"),
        skill_ids,
        point_ids,
        state_refs,
    )?;
    validate_expr_refs(
        &slot.complete_expr,
        &format!("{path}.complete_expr"),
        skill_ids,
        point_ids,
        state_refs,
    )?;
    validate_attempt_policy(&format!("{path}.attempt_policy"), &slot.attempt_policy)?;
    validate_runtime_actions(
        &format!("{path}.post_actions"),
        &slot.post_actions,
        state_refs,
    )?;

    Ok(())
}

fn validate_assist_lanes(
    rotation_index: usize,
    rotation: &CycleConfig,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let mut lane_ids = HashSet::new();
    for (lane_index, lane) in rotation.assist_lanes.iter().enumerate() {
        let lane_path = format!("rotations[{rotation_index}].assist_lanes[{lane_index}]");
        let lane_id = lane.id.trim();
        if lane_id.is_empty() {
            return Err(AppError::Config(format!(
                "{lane_path}.id must not be empty"
            )));
        }
        if !lane_ids.insert(lane_id) {
            return Err(AppError::Config(format!(
                "{lane_path}.id duplicates assist lane '{lane_id}'"
            )));
        }
        if lane.name.trim().is_empty() {
            return Err(AppError::Config(format!(
                "{lane_path}.name must not be empty"
            )));
        }
        if !(10..=600_000).contains(&lane.check_interval_ms) {
            return Err(AppError::Config(format!(
                "{lane_path}.check_interval_ms must be between 10 and 600000"
            )));
        }
        match lane.interrupt_policy {
            AssistInterruptPolicy::IdleOnly
            | AssistInterruptPolicy::CompleteWait
            | AssistInterruptPolicy::AnyWait => {}
        }
        for (slot_index, slot) in lane.skills.iter().enumerate() {
            validate_skill_slot_refs(
                &format!("{lane_path}.skills[{slot_index}]"),
                slot,
                skill_ids,
                point_ids,
                state_refs,
            )?;
        }
    }

    Ok(())
}

fn validate_observer_lanes(
    rotation_index: usize,
    rotation: &CycleConfig,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let mut lane_ids = HashSet::new();
    for (lane_index, lane) in rotation.observer_lanes.iter().enumerate() {
        let lane_path = format!("rotations[{rotation_index}].observer_lanes[{lane_index}]");
        let lane_id = lane.id.trim();
        if lane_id.is_empty() {
            return Err(AppError::Config(format!(
                "{lane_path}.id must not be empty"
            )));
        }
        if !lane_ids.insert(lane_id) {
            return Err(AppError::Config(format!(
                "{lane_path}.id duplicates observer lane '{lane_id}'"
            )));
        }
        if lane.name.trim().is_empty() {
            return Err(AppError::Config(format!(
                "{lane_path}.name must not be empty"
            )));
        }
        if !(10..=600_000).contains(&lane.check_interval_ms) {
            return Err(AppError::Config(format!(
                "{lane_path}.check_interval_ms must be between 10 and 600000"
            )));
        }
        for (slot_index, slot) in lane.actions.iter().enumerate() {
            validate_observer_action_slot(
                &format!("{lane_path}.actions[{slot_index}]"),
                slot,
                skill_ids,
                point_ids,
                state_refs,
            )?;
        }
    }

    Ok(())
}

fn validate_observer_action_slot(
    path: &str,
    slot: &ObserverActionSlot,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    if slot.id.trim().is_empty() {
        return Err(AppError::Config(format!("{path}.id must not be empty")));
    }
    if slot.label.trim().is_empty() {
        return Err(AppError::Config(format!("{path}.label must not be empty")));
    }
    validate_expr_refs(
        &slot.condition_expr,
        &format!("{path}.condition_expr"),
        skill_ids,
        point_ids,
        state_refs,
    )?;
    if slot.actions.is_empty() {
        return Err(AppError::Config(format!(
            "{path}.actions must not be empty"
        )));
    }
    validate_runtime_actions(&format!("{path}.actions"), &slot.actions, state_refs)?;
    Ok(())
}

struct StateRefs {
    marker_values: HashMap<String, HashSet<String>>,
    timer_ids: HashSet<String>,
    counter_ids: HashSet<String>,
}

fn validate_state_schema(
    rotation_index: usize,
    rotation: &crate::models::cycle::CycleConfig,
) -> AppResult<StateRefs> {
    let mut marker_values = HashMap::new();
    let mut timer_ids = HashSet::new();
    let mut counter_ids = HashSet::new();
    let Some(schema) = &rotation.state_schema else {
        return Ok(StateRefs {
            marker_values,
            timer_ids,
            counter_ids,
        });
    };
    for (marker_index, marker) in schema.markers.iter().enumerate() {
        let path = format!("rotations[{rotation_index}].state_schema.markers[{marker_index}]");
        let marker_id = marker.id.trim();
        if marker_id.is_empty() {
            return Err(AppError::Config(format!("{path}.id must not be empty")));
        }
        if marker.name.trim().is_empty() {
            return Err(AppError::Config(format!("{path}.name must not be empty")));
        }
        if marker.initial_value.trim().is_empty() {
            return Err(AppError::Config(format!(
                "{path}.initial_value must not be empty"
            )));
        }
        let mut values = HashSet::new();
        for value in &marker.allowed_values {
            let value = value.trim();
            if value.is_empty() {
                return Err(AppError::Config(format!(
                    "{path}.allowed_values must not contain empty values"
                )));
            }
            if !values.insert(value.to_string()) {
                return Err(AppError::Config(format!(
                    "{path}.allowed_values contains duplicate value '{value}'"
                )));
            }
        }
        if !values.is_empty() && !values.contains(marker.initial_value.trim()) {
            return Err(AppError::Config(format!(
                "{path}.initial_value '{}' is not allowed",
                marker.initial_value
            )));
        }
        if marker_values
            .insert(marker_id.to_string(), values)
            .is_some()
        {
            return Err(AppError::Config(format!(
                "duplicate marker id '{marker_id}' in rotations[{rotation_index}]"
            )));
        }
    }
    for (timer_index, timer) in schema.timers.iter().enumerate() {
        let path = format!("rotations[{rotation_index}].state_schema.timers[{timer_index}]");
        let timer_id = timer.id.trim();
        if timer_id.is_empty() {
            return Err(AppError::Config(format!("{path}.id must not be empty")));
        }
        if timer.name.trim().is_empty() {
            return Err(AppError::Config(format!("{path}.name must not be empty")));
        }
        if !timer_ids.insert(timer_id.to_string()) {
            return Err(AppError::Config(format!(
                "duplicate timer id '{timer_id}' in rotations[{rotation_index}]"
            )));
        }
    }
    for (counter_index, counter) in schema.counters.iter().enumerate() {
        let path = format!("rotations[{rotation_index}].state_schema.counters[{counter_index}]");
        let counter_id = counter.id.trim();
        if counter_id.is_empty() {
            return Err(AppError::Config(format!("{path}.id must not be empty")));
        }
        if counter.name.trim().is_empty() {
            return Err(AppError::Config(format!("{path}.name must not be empty")));
        }
        if !counter_ids.insert(counter_id.to_string()) {
            return Err(AppError::Config(format!(
                "duplicate counter id '{counter_id}' in rotations[{rotation_index}]"
            )));
        }
    }
    Ok(StateRefs {
        marker_values,
        timer_ids,
        counter_ids,
    })
}

fn validate_runtime_actions(
    path: &str,
    actions: &[RuntimeAction],
    state_refs: &StateRefs,
) -> AppResult<()> {
    for (index, action) in actions.iter().enumerate() {
        match action {
            RuntimeAction::SetMarker { marker_id, value } => {
                validate_marker_ref_value(
                    &format!("{path}[{index}]"),
                    marker_id,
                    value,
                    state_refs,
                )?;
            }
            RuntimeAction::ClearMarker { marker_id } => {
                let marker_id = marker_id.trim();
                if marker_id.is_empty() {
                    return Err(AppError::Config(format!(
                        "{path}[{index}].marker_id is empty"
                    )));
                }
                if !state_refs.marker_values.contains_key(marker_id) {
                    return Err(AppError::Config(format!(
                        "{path}[{index}] references missing marker '{marker_id}'"
                    )));
                }
            }
            RuntimeAction::RecordTimer { timer_id } | RuntimeAction::ResetTimer { timer_id } => {
                let timer_id = timer_id.trim();
                if timer_id.is_empty() {
                    return Err(AppError::Config(format!(
                        "{path}[{index}].timer_id is empty"
                    )));
                }
                if !state_refs.timer_ids.contains(timer_id) {
                    return Err(AppError::Config(format!(
                        "{path}[{index}] references missing timer '{timer_id}'"
                    )));
                }
            }
            RuntimeAction::IncrementCounter { counter_id, .. }
            | RuntimeAction::SetCounter { counter_id, .. }
            | RuntimeAction::ResetCounter { counter_id } => {
                let counter_id = counter_id.trim();
                if counter_id.is_empty() {
                    return Err(AppError::Config(format!(
                        "{path}[{index}].counter_id is empty"
                    )));
                }
                if !state_refs.counter_ids.contains(counter_id) {
                    return Err(AppError::Config(format!(
                        "{path}[{index}] references missing counter '{counter_id}'"
                    )));
                }
            }
        }
    }
    Ok(())
}

fn validate_marker_ref_value(
    path: &str,
    marker_id: &str,
    value: &str,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let marker_id = marker_id.trim();
    if marker_id.is_empty() {
        return Err(AppError::Config(format!("{path}.marker_id is empty")));
    }
    let Some(allowed_values) = state_refs.marker_values.get(marker_id) else {
        return Err(AppError::Config(format!(
            "{path} references missing marker '{marker_id}'"
        )));
    };
    if !allowed_values.is_empty() && !allowed_values.contains(value.trim()) {
        return Err(AppError::Config(format!(
            "{path}.value '{}' is not allowed for marker '{marker_id}'",
            value
        )));
    }
    Ok(())
}

fn validate_attempt_policy(
    path: &str,
    policy: &Option<crate::models::cycle::AttemptPolicy>,
) -> AppResult<()> {
    let Some(policy) = policy else {
        return Ok(());
    };
    if policy.max_attempts == 0 || policy.max_attempts > 21 {
        return Err(AppError::Config(format!(
            "{path}.max_attempts must be between 1 and 21"
        )));
    }
    if policy.start_timeout_ms == 0 || policy.start_timeout_ms > 600_000 {
        return Err(AppError::Config(format!(
            "{path}.start_timeout_ms must be between 1 and 600000"
        )));
    }
    if policy.complete_timeout_ms > 600_000 {
        return Err(AppError::Config(format!(
            "{path}.complete_timeout_ms must be between 0 and 600000"
        )));
    }
    if policy.retry_delay_ms > 60_000 {
        return Err(AppError::Config(format!(
            "{path}.retry_delay_ms must be between 0 and 60000"
        )));
    }
    match policy.failure_policy.trim() {
        "hold_phase" | "next_slot" | "next_phase" => {}
        other => {
            return Err(AppError::Config(format!(
                "{path}.failure_policy has invalid value '{other}'"
            )));
        }
    }
    match policy.complete_fallback.trim() {
        "fail" | "assume_success_after_timeout" => {}
        other => {
            return Err(AppError::Config(format!(
                "{path}.complete_fallback has invalid value '{other}'"
            )));
        }
    }
    Ok(())
}

fn validate_pixel_spec(path: &str, pixel: &PixelSpec) -> AppResult<()> {
    if pixel.monitor.trim().is_empty() {
        return Err(AppError::Config(format!("{path}.monitor is empty")));
    }
    validate_sample_config(&format!("{path}.sample"), &pixel.sample)
}

fn validate_sample_config(path: &str, sample: &SampleConfig) -> AppResult<()> {
    match sample.mode.trim() {
        "single" | "mean_square" => Ok(()),
        mode => Err(AppError::Config(format!(
            "{path}.mode must be single or mean_square, got '{mode}'"
        ))),
    }
}

fn validate_expr_refs(
    expr: &Option<serde_json::Value>,
    path: &str,
    skill_ids: &HashSet<&str>,
    point_ids: &HashSet<&str>,
    state_refs: &StateRefs,
) -> AppResult<()> {
    let Some(expr) = expr else {
        return Ok(());
    };
    let compiled = compile_expr_json(expr, path);
    if let Some(diagnostic) = compiled
        .diagnostics
        .iter()
        .find(|diagnostic| diagnostic.is_error())
    {
        return Err(AppError::Config(format!(
            "{}: {}",
            diagnostic.path, diagnostic.code
        )));
    }
    for point_id in compiled.probes.point_ids {
        if !point_ids.contains(point_id.as_str()) {
            return Err(AppError::Config(format!(
                "{path} references missing point '{point_id}'"
            )));
        }
    }
    for skill_id in compiled
        .probes
        .skill_pixel_ids
        .into_iter()
        .chain(compiled.probes.skill_metric_ids)
    {
        if !skill_ids.contains(skill_id.as_str()) {
            return Err(AppError::Config(format!(
                "{path} references missing skill '{skill_id}'"
            )));
        }
    }
    for timer_id in compiled.probes.timer_ids {
        if !state_refs.timer_ids.contains(timer_id.as_str()) {
            return Err(AppError::Config(format!(
                "{path} references missing timer '{timer_id}'"
            )));
        }
    }
    for marker_ref in compiled.probes.marker_refs {
        validate_marker_ref_value(path, &marker_ref.marker_id, &marker_ref.value, state_refs)?;
    }
    for counter_id in compiled.probes.counter_ids {
        if !state_refs.counter_ids.contains(counter_id.as_str()) {
            return Err(AppError::Config(format!(
                "{path} references missing counter '{counter_id}'"
            )));
        }
    }
    Ok(())
}

fn app_data_dir() -> AppResult<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        let local = std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."));
        Ok(local.join("game-macro-tauri"))
    }
    #[cfg(not(target_os = "windows"))]
    {
        let dir = dirs::data_dir()
            .ok_or_else(|| AppError::Config("unable to determine data directory".into()))?;
        Ok(dir.join("game-macro-tauri"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::cycle::{
        AssistInterruptPolicy, AssistLaneConfig, AttemptPolicy, CycleConfig, CyclePhase,
        CycleStateSchema, PhaseFallbackTransition, PhaseTransitionRule, RuntimeAction,
        RuntimeCounterDef, RuntimeMarkerDef, RuntimeTimerDef, SkillSlot,
    };
    use crate::models::point::Point;
    use crate::models::skill::{AmmoStagePixel, PixelSpec, SampleConfig, Skill};
    use crate::store::profile_store::default_profile;
    use serde_json::json;

    fn profile_with_slot(slot: SkillSlot) -> Profile {
        let mut profile = default_profile("default");
        profile.rotations = vec![CycleConfig {
            name: "test".into(),
            phases: vec![CyclePhase {
                name: "P1".into(),
                skills: vec![slot],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 100,
            max_cycles: 0,
            state_schema: None,
        }];
        profile
    }

    fn valid_point(id: &str) -> Point {
        Point {
            id: id.into(),
            name: id.into(),
            monitor: "primary".into(),
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
            ..Default::default()
        }
    }

    fn valid_skill(id: &str) -> Skill {
        Skill {
            id: id.into(),
            name: id.into(),
            pixel: PixelSpec {
                monitor: "primary".into(),
                sample: SampleConfig {
                    mode: "single".into(),
                    radius: 0,
                },
                ..Default::default()
            },
            ..Default::default()
        }
    }

    #[test]
    fn test_reference_validation_rejects_missing_slot_skill() {
        let profile = profile_with_slot(SkillSlot {
            skill_id: "missing".into(),
            priority: 1,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_invalid_assist_lane() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });
        profile.skills.skills.push(valid_skill("sk1"));
        profile.rotations[0].assist_lanes = vec![AssistLaneConfig {
            id: "assist".into(),
            name: "Assist".into(),
            enabled: true,
            check_interval_ms: 5,
            interrupt_policy: AssistInterruptPolicy::IdleOnly,
            skills: vec![SkillSlot {
                skill_id: "missing".into(),
                priority: 1,
                label: String::new(),
                condition_expr: None,
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
        }];

        let err = validate_profile_references(&profile).expect_err("assist lane must be invalid");
        assert!(matches!(err, AppError::Config(_)));
    }

    #[test]
    fn test_reference_validation_rejects_missing_expr_point() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "pixel_point",
                "point_id": "missing",
                "tolerance": 10
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });
        profile.points.points.clear();

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_invalid_attempt_policy() {
        let profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: Some(AttemptPolicy {
                max_attempts: 0,
                start_timeout_ms: 0,
                complete_timeout_ms: 0,
                retry_delay_ms: 0,
                failure_policy: "next_slot".into(),
                complete_fallback: "assume_success_after_timeout".into(),
            }),
            post_actions: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_missing_timer_expr_ref() {
        let profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "timer_elapsed_ge",
                "timer_id": "missing",
                "ms": 1000
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_accepts_declared_timer_action_and_expr() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "timer_elapsed_ge",
                "timer_id": "burst",
                "ms": 1000
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![RuntimeAction::RecordTimer {
                timer_id: "burst".into(),
            }],
        });
        profile.rotations[0].state_schema = Some(CycleStateSchema {
            markers: vec![],
            timers: vec![RuntimeTimerDef {
                id: "burst".into(),
                name: "Burst".into(),
                reset_on_cycle_start: false,
            }],
            counters: vec![],
        });

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_rejects_missing_marker_expr_ref() {
        let profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "marker_eq",
                "marker_id": "missing",
                "value": "main"
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_marker_value_outside_allowed_set() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "marker_eq",
                "marker_id": "weapon",
                "value": "unknown"
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });
        profile.rotations[0].state_schema = Some(CycleStateSchema {
            markers: vec![RuntimeMarkerDef {
                id: "weapon".into(),
                name: "Weapon".into(),
                initial_value: "main".into(),
                allowed_values: vec!["main".into(), "alt".into()],
            }],
            timers: vec![],
            counters: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_accepts_declared_marker_action_and_expr() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "marker_eq",
                "marker_id": "weapon",
                "value": "alt"
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![RuntimeAction::SetMarker {
                marker_id: "weapon".into(),
                value: "alt".into(),
            }],
        });
        profile.rotations[0].state_schema = Some(CycleStateSchema {
            markers: vec![RuntimeMarkerDef {
                id: "weapon".into(),
                name: "Weapon".into(),
                initial_value: "main".into(),
                allowed_values: vec!["main".into(), "alt".into()],
            }],
            timers: vec![],
            counters: vec![],
        });

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_rejects_missing_counter_expr_ref() {
        let profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "counter_ge",
                "counter_id": "missing",
                "value": 1
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_accepts_declared_counter_action_and_expr() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: Some(json!({
                "type": "counter_ge",
                "counter_id": "main_wp2_count",
                "value": 2
            })),
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![RuntimeAction::IncrementCounter {
                counter_id: "main_wp2_count".into(),
                by: 1,
            }],
        });
        profile.rotations[0].state_schema = Some(CycleStateSchema {
            markers: vec![],
            timers: vec![],
            counters: vec![RuntimeCounterDef {
                id: "main_wp2_count".into(),
                name: "Main WP2 Count".into(),
                initial_value: 0,
                reset_on_phase_entry: false,
                reset_on_cycle_start: true,
            }],
        });

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_rejects_missing_phase_transition_target() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });
        profile.rotations[0].phases[0].name = "P1".into();
        profile.rotations[0].phases[0].transition_rules = vec![PhaseTransitionRule {
            label: "missing".into(),
            condition_expr: Some(json!({"type": "const", "value": true})),
            target_phase: "Missing".into(),
        }];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_accepts_declared_phase_transition_target() {
        let mut profile = profile_with_slot(SkillSlot {
            skill_id: String::new(),
            priority: 1,
            label: String::new(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        });
        profile.rotations[0].phases[0].name = "P1".into();
        profile.rotations[0].phases[0].transition_rules = vec![PhaseTransitionRule {
            label: "to-p2".into(),
            condition_expr: Some(json!({"type": "const", "value": true})),
            target_phase: "P2".into(),
        }];
        profile.rotations[0].phases[0].fallback_transition = Some(PhaseFallbackTransition::Phase {
            target_phase: "P2".into(),
        });
        profile.rotations[0].phases.push(CyclePhase {
            name: "P2".into(),
            skills: vec![],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        });

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_rejects_duplicate_skill_ids() {
        let mut profile = default_profile("default");
        profile.skills.skills = vec![valid_skill("same"), valid_skill("same")];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_duplicate_point_ids() {
        let mut profile = default_profile("default");
        profile.points.points = vec![valid_point("same"), valid_point("same")];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_missing_cast_bar_point() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.mode = "pixel".into();
        profile.base.cast_bar.point_id = "missing".into();

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_accepts_existing_cast_bar_point() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.mode = "pixel".into();
        profile.base.cast_bar.point_id = "cast".into();
        profile.points.points = vec![valid_point("cast")];

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_accepts_cast_bar_roi_without_point() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.mode = "roi".into();
        profile.base.cast_bar.point_id.clear();
        profile.base.cast_bar.roi.enabled = true;
        profile.base.cast_bar.roi.monitor = "primary".into();
        profile.base.cast_bar.roi.width = 320;
        profile.base.cast_bar.roi.height = 28;

        assert!(validate_profile_references(&profile).is_ok());
    }

    #[test]
    fn test_reference_validation_rejects_invalid_cast_bar_roi_dimensions() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.roi.enabled = true;
        profile.base.cast_bar.roi.width = 0;
        profile.base.cast_bar.roi.height = 0;

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_empty_point_name() {
        let mut profile = default_profile("default");
        profile.points.points = vec![Point {
            id: "point-1".into(),
            monitor: "primary".into(),
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
            ..Default::default()
        }];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_invalid_point_sample_mode() {
        let mut profile = default_profile("default");
        let mut point = valid_point("point-1");
        point.sample.mode = "median".into();
        profile.points.points = vec![point];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_empty_skill_name() {
        let mut profile = default_profile("default");
        profile.skills.skills = vec![Skill {
            id: "skill-1".into(),
            pixel: crate::models::skill::PixelSpec {
                monitor: "primary".into(),
                sample: SampleConfig {
                    mode: "single".into(),
                    radius: 0,
                },
                ..Default::default()
            },
            ..Default::default()
        }];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_duplicate_ammo_charges() {
        let mut profile = default_profile("default");
        profile.skills.skills = vec![Skill {
            ammo_stages: vec![
                AmmoStagePixel {
                    charges_left: 1,
                    pixel: PixelSpec {
                        monitor: "primary".into(),
                        sample: SampleConfig {
                            mode: "single".into(),
                            radius: 0,
                        },
                        ..Default::default()
                    },
                },
                AmmoStagePixel {
                    charges_left: 1,
                    pixel: PixelSpec {
                        monitor: "primary".into(),
                        sample: SampleConfig {
                            mode: "single".into(),
                            radius: 0,
                        },
                        ..Default::default()
                    },
                },
            ],
            ..valid_skill("skill-1")
        }];

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_conflicting_hotkeys() {
        let mut profile = default_profile("default");
        profile.base.pick.confirm_hotkey = "f9".into();
        profile.base.exec.toggle_hotkey = "F9".into();

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_invalid_cast_bar_mode() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.mode = "unknown".into();

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_zero_cast_bar_poll_interval() {
        let mut profile = default_profile("default");
        profile.base.cast_bar.poll_interval_ms = 0;

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_invalid_exec_retry_count() {
        let mut profile = default_profile("default");
        profile.base.exec.max_retries = 21;

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }

    #[test]
    fn test_reference_validation_rejects_zero_rotation_poll_interval() {
        let mut profile = default_profile("default");
        profile.rotations[0].poll_interval_ms = 0;

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
    }
}
