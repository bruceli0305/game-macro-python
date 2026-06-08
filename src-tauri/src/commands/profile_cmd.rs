//! Profile 配置 CRUD 命令

use crate::ast::compiler::compile_expr_json;
use crate::error::{AppError, AppResult, CommandResult};
use crate::models::profile::Profile;
use crate::models::skill::{PixelSpec, SampleConfig};
use crate::store::profile_store::ProfileStore;
use serde::Serialize;
use std::collections::HashSet;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct ProfileInfo {
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
    if profile.base.cast_bar.mode != "timer" {
        if cast_bar_point_id.is_empty() {
            return Err(AppError::Config(
                "base.cast_bar.point_id is required when cast bar mode is not timer".into(),
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
        for (phase_index, phase) in rotation.phases.iter().enumerate() {
            for (slot_index, slot) in phase.skills.iter().enumerate() {
                let path = format!(
                    "rotations[{rotation_index}].phases[{phase_index}].skills[{slot_index}]"
                );
                let skill_id = slot.skill_id.trim();
                if !skill_id.is_empty() && !skill_ids.contains(skill_id) {
                    return Err(AppError::Config(format!(
                        "{path}.skill_id references missing skill '{skill_id}'"
                    )));
                }

                validate_expr_refs(
                    &slot.condition_expr,
                    &format!("{path}.condition_expr"),
                    &skill_ids,
                    &point_ids,
                )?;
                validate_expr_refs(
                    &slot.start_expr,
                    &format!("{path}.start_expr"),
                    &skill_ids,
                    &point_ids,
                )?;
                validate_expr_refs(
                    &slot.complete_expr,
                    &format!("{path}.complete_expr"),
                    &skill_ids,
                    &point_ids,
                )?;
            }
        }
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
        "timer" | "pixel" => {}
        mode => {
            return Err(AppError::Config(format!(
                "base.cast_bar.mode must be timer or pixel, got '{mode}'"
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

fn validate_rotation_config(rotation_index: usize, poll_interval_ms: u32) -> AppResult<()> {
    if poll_interval_ms == 0 || poll_interval_ms > 10000 {
        return Err(AppError::Config(format!(
            "rotations[{rotation_index}].poll_interval_ms must be between 1 and 10000"
        )));
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
    use crate::models::cycle::{CycleConfig, CyclePhase, SkillSlot};
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
            }],
            poll_interval_ms: 100,
            max_cycles: 0,
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
        });

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
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
        });
        profile.points.points.clear();

        assert!(matches!(
            validate_profile_references(&profile),
            Err(AppError::Config(_))
        ));
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
