//! Offline cycle simulation helpers.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::ast::evaluator::{CastBarRoiProvider, PixelSampler};
use crate::capture::capturer::DirectPixelSampler;
use crate::capture::cast_bar_roi::ScreenCastBarRoiProvider;
use crate::engine::cycle_executor::CycleExecutor;
use crate::engine::profile_config::{
    load_active_engine_profile, parse_profile_content, simulation_inputs_from_profile,
};
use crate::engine::skill_attempt::{KeySender, SkillAttemptConfig};
use crate::error::{AppError, AppResult};
use crate::models::cycle::{CycleConfig, CyclePhase, SkillSlot, SkillSlotRole};
use crate::models::point::Point;
use crate::models::profile::Profile;
use crate::models::skill::{CastConfig, ColorRGB, PixelSpec, SampleConfig, Skill};
use crate::store::profile_store::default_profile;

#[derive(Debug, Clone, Deserialize)]
pub struct PixelOverride {
    pub monitor: String,
    pub x: i32,
    pub y: i32,
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

pub(crate) struct OverridePixelSampler {
    pixels: HashMap<(String, i32, i32), (u8, u8, u8)>,
}

#[derive(Debug, Clone, Serialize)]
struct IpcSmokeFixtureSummary {
    profile_id: String,
    direct_events: usize,
    pixel_events: usize,
}

impl OverridePixelSampler {
    pub(crate) fn new(overrides: Vec<PixelOverride>) -> Self {
        let pixels = overrides
            .into_iter()
            .map(|item| ((item.monitor, item.x, item.y), (item.r, item.g, item.b)))
            .collect();
        Self { pixels }
    }
}

impl PixelSampler for OverridePixelSampler {
    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        _sample_mode: &str,
        _sample_radius: u8,
    ) -> Option<(u8, u8, u8)> {
        self.pixels
            .get(&(monitor.to_string(), x_abs, y_abs))
            .copied()
    }
}

pub(crate) fn simulate_active_rotation() -> AppResult<String> {
    let input = load_active_engine_profile(false)?;
    let sampler = DirectPixelSampler;
    simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &sampler,
        input.attempt_cfg,
    )
}

pub(crate) fn simulate_active_rotation_with_pixels(
    pixel_overrides: Vec<PixelOverride>,
) -> AppResult<String> {
    let input = load_active_engine_profile(false)?;
    let sampler = OverridePixelSampler::new(pixel_overrides);
    simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &sampler,
        input.attempt_cfg,
    )
}

pub(crate) fn simulate_profile_rotation(content: String) -> AppResult<String> {
    let profile = parse_profile_content(&content)?;
    let input = simulation_inputs_from_profile(profile)?;

    let sampler = DirectPixelSampler;
    simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &sampler,
        input.attempt_cfg,
    )
}

pub(crate) fn simulate_profile_rotation_with_pixels(
    content: String,
    pixel_overrides: Vec<PixelOverride>,
) -> AppResult<String> {
    let profile = parse_profile_content(&content)?;
    let input = simulation_inputs_from_profile(profile)?;
    let sampler = OverridePixelSampler::new(pixel_overrides);
    simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &sampler,
        input.attempt_cfg,
    )
}

pub(crate) fn simulate_ipc_smoke_fixture() -> AppResult<String> {
    let profile = smoke_fixture_profile();

    let mut direct_profile = profile.clone();
    if let Some(slot) = direct_profile
        .rotations
        .get_mut(0)
        .and_then(|rotation| rotation.phases.get_mut(0))
        .and_then(|phase| phase.skills.get_mut(0))
    {
        slot.condition_expr = None;
    }

    let input = simulation_inputs_from_profile(direct_profile)?;
    let direct_sampler = DirectPixelSampler;
    let direct_json = simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &direct_sampler,
        input.attempt_cfg,
    )?;

    let input = simulation_inputs_from_profile(profile.clone())?;
    let pixel_sampler = OverridePixelSampler::new(smoke_fixture_pixel_overrides());
    let pixel_json = simulate_rotation_with_sampler(
        &input.config,
        &input.skills,
        &input.points,
        &pixel_sampler,
        input.attempt_cfg,
    )?;

    let summary = IpcSmokeFixtureSummary {
        profile_id: profile.meta.profile_id,
        direct_events: event_count_from_simulation_json(&direct_json)?,
        pixel_events: event_count_from_simulation_json(&pixel_json)?,
    };

    serde_json::to_string_pretty(&summary).map_err(AppError::from)
}

pub(crate) fn simulate_rotation_with_sampler(
    config: &CycleConfig,
    skills: &[Skill],
    points: &[Point],
    sampler: &dyn PixelSampler,
    attempt_cfg: SkillAttemptConfig,
) -> AppResult<String> {
    let roi_provider = attempt_cfg
        .cast_bar_roi
        .clone()
        .map(ScreenCastBarRoiProvider::new);
    let mut executor = CycleExecutor::new(config, points, skills, sampler, attempt_cfg)
        .with_cast_bar_roi_provider(
            roi_provider
                .as_ref()
                .map(|provider| provider as &dyn CastBarRoiProvider),
        );

    struct NoopKeySender;
    impl KeySender for NoopKeySender {
        fn send_key(&mut self, _: &str) -> bool {
            true
        }
    }
    let mut key_sender = NoopKeySender;

    let mut sim_events: Vec<serde_json::Value> = Vec::new();
    let max_ticks = 80;
    let mut time_ms: u64 = 0;
    let mut log_cursor = 0usize;

    for _tick in 0..max_ticks {
        let acted = executor.tick(&mut key_sender, &|| false, time_ms);

        for log in &executor.log[log_cursor..] {
            let skill = skills.iter().find(|skill| skill.id == log.skill_id);
            let cast_ms = skill.map(|skill| skill.cast.readbar_ms).unwrap_or(0) as u64;
            let cd_ms = skill.map(|skill| skill.cooldown_ms).unwrap_or(0) as u64;

            sim_events.push(serde_json::json!({
                "index": sim_events.len() + 1,
                "timeMs": log.ts_ms,
                "phase": log.phase_name,
                "event": log.event,
                "skillId": log.skill_id,
                "skillName": log.skill_name,
                "outcome": log.outcome,
                "castMs": cast_ms,
                "cdMs": cd_ms,
                "reason": log.reason,
            }));
        }
        log_cursor = executor.log.len();

        if acted {
            let gap = 50_u64;
            let cast_ms = skills
                .iter()
                .find(|skill| skill.id == executor.state.last_skill_id)
                .map(|skill| skill.cast.readbar_ms)
                .unwrap_or(0) as u64;
            time_ms += cast_ms.max(1) + gap;
        } else {
            time_ms += config.poll_interval_ms as u64;
        }
    }

    serde_json::to_string_pretty(&serde_json::json!({ "events": sim_events }))
        .map_err(AppError::from)
}

fn event_count_from_simulation_json(content: &str) -> AppResult<usize> {
    let value: serde_json::Value = serde_json::from_str(content)?;
    let events = value
        .get("events")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| AppError::Engine("simulation response missing events array".into()))?;
    Ok(events.len())
}

fn smoke_fixture_profile() -> Profile {
    let mut profile = default_profile("ipc-smoke");
    profile.points.points = vec![Point {
        id: "smoke-point".into(),
        name: "IPC smoke point".into(),
        monitor: "primary".into(),
        vx: 10,
        vy: 20,
        color: ColorRGB {
            r: 12,
            g: 34,
            b: 56,
        },
        tolerance: 0,
        sample: SampleConfig {
            mode: "single".into(),
            radius: 0,
        },
        captured_at: "ipc-smoke".into(),
        note: "IPC smoke fixture".into(),
    }];
    profile.skills.skills = vec![Skill {
        id: "smoke-skill".into(),
        name: "IPC smoke skill".into(),
        enabled: true,
        trigger_key: "1".into(),
        cast: CastConfig {
            readbar_ms: 0,
            cooldown_ms: 0,
        },
        pixel: PixelSpec {
            monitor: "primary".into(),
            vx: 30,
            vy: 40,
            color: ColorRGB {
                r: 90,
                g: 120,
                b: 150,
            },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
        },
        note: "IPC smoke fixture".into(),
        game_id: 0,
        game_desc: String::new(),
        icon_url: String::new(),
        cooldown_ms: 0,
        radius: 0,
        shots_per_cycle: 1,
        ammo_stages: vec![],
    }];
    profile.rotations = vec![CycleConfig {
        name: "IPC smoke rotation".into(),
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 1,
        state_schema: None,
        phases: vec![CyclePhase {
            name: "P1".into(),
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
            skills: vec![SkillSlot {
                skill_id: "smoke-skill".into(),
                priority: 1,
                label: "smoke-skill".into(),
                slot_role: SkillSlotRole::Mandatory,
                condition_expr: Some(serde_json::json!({
                    "type": "pixel_point",
                    "point_id": "smoke-point",
                    "tolerance": 0
                })),
                readiness_expr: None,
                readiness_policy: Default::default(),
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
        }],
    }];
    profile
}

fn smoke_fixture_pixel_overrides() -> Vec<PixelOverride> {
    vec![PixelOverride {
        monitor: "primary".into(),
        x: 10,
        y: 20,
        r: 12,
        g: 34,
        b: 56,
    }]
}
