//! Profile 配置 CRUD 命令

use crate::ast::compiler::compile_expr_json;
use crate::error::{AppError, AppResult, CommandResult};
use crate::models::profile::Profile;
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
    let skill_ids: HashSet<&str> = profile
        .skills
        .skills
        .iter()
        .map(|skill| skill.id.as_str())
        .filter(|id| !id.trim().is_empty())
        .collect();
    let point_ids: HashSet<&str> = profile
        .points
        .points
        .iter()
        .map(|point| point.id.as_str())
        .filter(|id| !id.trim().is_empty())
        .collect();

    for (rotation_index, rotation) in profile.rotations.iter().enumerate() {
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
}
