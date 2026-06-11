//! Profile loading and validation helpers used by engine commands and simulation.

use serde::Serialize;

use crate::engine::skill_attempt::SkillAttemptConfig;
use crate::error::{AppError, AppResult};
use crate::models::base::BaseConfig;
use crate::models::cycle::CycleConfig;
use crate::models::point::Point;
use crate::models::profile::Profile;
use crate::models::skill::Skill;
use crate::profile::validation::validate_profile_references;
use crate::store::profile_store::{ProfileStore, app_data_dir};

#[derive(Debug, Clone, Serialize)]
pub struct EnginePreflightReport {
    pub ready: bool,
    pub engine_running: bool,
    pub profile_name: String,
    pub exec_enabled: bool,
    pub rotation_count: usize,
    pub skill_count: usize,
    pub point_count: usize,
    pub executable_slot_count: usize,
    pub error: Option<String>,
}

pub(crate) struct EngineProfileInput {
    pub config: CycleConfig,
    pub skills: Vec<Skill>,
    pub points: Vec<Point>,
    pub attempt_cfg: SkillAttemptConfig,
}

pub(crate) fn load_active_engine_profile(
    require_exec_enabled: bool,
) -> AppResult<EngineProfileInput> {
    let dir = app_data_dir()?;
    let store = ProfileStore::new(dir);
    let (profile_name, profile) = store.load_active_or_default()?;

    let input = engine_input_from_profile(profile, require_exec_enabled, "profile")?;

    tracing::info!(
        "loaded profile '{}': {} phases, {} skills",
        profile_name,
        input.config.phases.len(),
        input.skills.len()
    );

    Ok(input)
}

pub(crate) fn load_active_preflight_report(
    engine_running: bool,
) -> AppResult<EnginePreflightReport> {
    let dir = app_data_dir()?;
    let store = ProfileStore::new(dir);
    let (_profile_name, profile) = store.load_active_or_default()?;
    Ok(preflight_report_from_profile(&profile, engine_running))
}

pub(crate) fn parse_profile_content(content: &str) -> AppResult<Profile> {
    serde_json::from_str(content).map_err(AppError::from)
}

pub(crate) fn simulation_inputs_from_profile(profile: Profile) -> AppResult<EngineProfileInput> {
    engine_input_from_profile(profile, false, "profile")
}

fn engine_input_from_profile(
    profile: Profile,
    require_exec_enabled: bool,
    profile_label: &str,
) -> AppResult<EngineProfileInput> {
    validate_profile_for_engine(&profile, require_exec_enabled)?;
    let attempt_cfg = attempt_config_from_base(&profile.base);

    let config = profile
        .rotations
        .into_iter()
        .next()
        .ok_or_else(|| AppError::Config(format!("{profile_label} has no rotations")))?;

    Ok(EngineProfileInput {
        config,
        skills: profile.skills.skills,
        points: profile.points.points,
        attempt_cfg,
    })
}

pub(crate) fn attempt_config_from_base(base: &BaseConfig) -> SkillAttemptConfig {
    let cast_bar_roi =
        (base.cast_bar.roi.enabled || base.cast_bar.mode.trim() == "roi").then(|| {
            let mut roi = base.cast_bar.roi.clone();
            if base.cast_bar.mode.trim() == "roi" {
                roi.enabled = true;
            }
            roi
        });
    SkillAttemptConfig {
        default_gap_ms: base.exec.default_skill_gap_ms,
        poll_not_ready_ms: base.exec.poll_not_ready_ms,
        max_retries: base.exec.max_retries,
        retry_gap_ms: base.exec.retry_gap_ms,
        complete_poll_ms: base.cast_bar.poll_interval_ms,
        complete_max_wait_factor: base.cast_bar.max_wait_factor,
        cast_bar_roi,
        ..SkillAttemptConfig::default()
    }
}

pub(crate) fn validate_engine_profile(
    profile: &Profile,
    require_exec_enabled: bool,
) -> AppResult<()> {
    if require_exec_enabled && !profile.base.exec.enabled {
        return Err(AppError::Config(
            "macro execution is disabled in base.exec.enabled".into(),
        ));
    }

    let rotation = profile
        .rotations
        .first()
        .ok_or_else(|| AppError::Config("profile has no rotations".into()))?;
    if rotation.phases.is_empty() {
        return Err(AppError::Config("rotation has no phases".to_string()));
    }

    let mut has_executable_slot = false;
    for phase in &rotation.phases {
        for slot in &phase.skills {
            let skill_id = slot.skill_id.trim();
            if skill_id.is_empty() {
                continue;
            }
            let Some(skill) = profile
                .skills
                .skills
                .iter()
                .find(|skill| skill.id.as_str() == skill_id)
            else {
                return Err(AppError::Config(format!(
                    "slot references missing skill '{skill_id}'"
                )));
            };
            if !skill.enabled {
                continue;
            }
            if skill.trigger_key.trim().is_empty() {
                return Err(AppError::Config(format!(
                    "enabled skill '{}' has no trigger_key",
                    skill.id
                )));
            }
            has_executable_slot = true;
        }
    }

    if !has_executable_slot {
        return Err(AppError::Config(
            "rotation has no executable enabled skill slots".into(),
        ));
    }

    Ok(())
}

pub(crate) fn validate_profile_for_engine(
    profile: &Profile,
    require_exec_enabled: bool,
) -> AppResult<()> {
    validate_profile_references(profile)?;
    validate_engine_profile(profile, require_exec_enabled)
}

fn count_executable_slots(profile: &Profile) -> usize {
    let Some(rotation) = profile.rotations.first() else {
        return 0;
    };

    rotation
        .phases
        .iter()
        .flat_map(|phase| phase.skills.iter())
        .filter(|slot| {
            let skill_id = slot.skill_id.trim();
            if skill_id.is_empty() {
                return false;
            }
            profile.skills.skills.iter().any(|skill| {
                skill.id.as_str() == skill_id
                    && skill.enabled
                    && !skill.trigger_key.trim().is_empty()
            })
        })
        .count()
}

pub(crate) fn preflight_report_from_profile(
    profile: &Profile,
    engine_running: bool,
) -> EnginePreflightReport {
    let validation = validate_profile_for_engine(profile, true);
    EnginePreflightReport {
        ready: validation.is_ok() && !engine_running,
        engine_running,
        profile_name: profile.meta.profile_name.clone(),
        exec_enabled: profile.base.exec.enabled,
        rotation_count: profile.rotations.len(),
        skill_count: profile.skills.skills.len(),
        point_count: profile.points.points.len(),
        executable_slot_count: count_executable_slots(profile),
        error: if engine_running {
            Some("engine already running".into())
        } else {
            validation.err().map(|error| error.to_string())
        },
    }
}
