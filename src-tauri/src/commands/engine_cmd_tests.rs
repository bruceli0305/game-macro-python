use super::*;
use crate::ast::evaluator::CastBarRoiStats;
use crate::engine::profile_config::{
    attempt_config_from_base, preflight_report_from_profile, validate_engine_profile,
    validate_profile_for_engine,
};
use crate::engine::runtime_state::RuntimeState;
use crate::engine::simulation::{OverridePixelSampler, simulate_rotation_with_sampler};
use crate::error::AppError;
use crate::models::cycle::{CyclePhase, SkillSlot, SkillSlotRole};
use crate::models::point::Point;
use crate::models::profile::Profile;
use crate::models::skill::{CastConfig, ColorRGB, PixelSpec, SampleConfig};
use crate::store::profile_store::default_profile;

#[test]
fn test_runtime_payload_maps_skill_metrics() {
    let config = CycleConfig {
        name: "default".into(),
        phases: vec![],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: None,
    };
    let mut runtime = RuntimeState::new();
    runtime.engine_started("default");
    runtime.mark_attempt_started("skill-1");
    runtime.mark_success("skill-1");

    let payload = runtime_payload(RuntimePayloadInput {
        runtime: &runtime,
        config: &config,
        skills: &[],
        total_executed: 1,
        cycle_count: 2,
        phase_index: 0,
        uptime_ms: 123,
        cast_bar_roi: Some(CastBarRoiStats {
            enabled: true,
            sample_count: 3,
            cache_hit_count: 2,
            failed_sample_count: 1,
            last_latency_us: 1200,
            avg_latency_us: 900,
            max_latency_us: 1500,
            last_changed_ratio: 0.25,
            last_border_match_ratio: 0.5,
            last_changed_from_baseline: true,
            last_border_visible: false,
            last_gone: false,
            last_error: String::new(),
        }),
    });

    assert!(payload.running);
    assert_eq!(payload.total_executed, 1);
    assert_eq!(payload.cycle_count, 2);
    assert_eq!(payload.uptime_ms, 123);
    assert_eq!(payload.skills.len(), 1);
    assert_eq!(payload.skills[0].skill_id, "skill-1");
    assert_eq!(payload.skills[0].state, "SUCCESS");
    assert_eq!(payload.skills[0].attempt_started, 1);
    assert_eq!(payload.skills[0].success, 1);
    let roi = payload.cast_bar_roi.unwrap();
    assert_eq!(roi.sample_count, 3);
    assert_eq!(roi.cache_hit_count, 2);
    assert_eq!(roi.avg_latency_us, 900);
}

fn test_skill(id: &str, key: &str, enabled: bool) -> Skill {
    Skill {
        id: id.into(),
        name: id.into(),
        enabled,
        trigger_key: key.into(),
        cast: CastConfig::default(),
        pixel: PixelSpec {
            monitor: "primary".into(),
            vx: 0,
            vy: 0,
            color: ColorRGB { r: 0, g: 0, b: 0 },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
        },
        note: String::new(),
        game_id: 0,
        game_desc: String::new(),
        icon_url: String::new(),
        cooldown_ms: 0,
        radius: 0,
        shots_per_cycle: 1,
        ammo_stages: vec![],
    }
}

fn profile_with_slot(skill_id: &str) -> Profile {
    let mut profile = default_profile("default");
    profile.skills.skills = vec![test_skill(skill_id, "1", true)];
    profile.rotations[0].phases = vec![CyclePhase {
        name: "P1".into(),
        skills: vec![SkillSlot {
            skill_id: skill_id.into(),
            priority: 1,
            label: String::new(),
            slot_role: SkillSlotRole::Mandatory,
            readiness_expr: None,
            readiness_policy: Default::default(),
            condition_expr: None,
            start_expr: None,
            complete_expr: None,
            override_cast_ms: None,
            protected_release: false,
            attempt_policy: None,
            post_actions: vec![],
        }],
        complete_when: "any_fired".into(),
        entry_actions: vec![],
        transition_rules: vec![],
        fallback_transition: None,
    }];
    profile
}

#[test]
fn test_engine_profile_validation_rejects_empty_default() {
    let profile = default_profile("default");

    assert!(matches!(
        validate_engine_profile(&profile, false),
        Err(AppError::Config(_))
    ));
}

#[test]
fn test_engine_profile_validation_accepts_enabled_slot_with_key() {
    let profile = profile_with_slot("skill-1");

    assert!(validate_engine_profile(&profile, false).is_ok());
}

#[test]
fn test_engine_profile_validation_rejects_disabled_execution_for_start() {
    let profile = profile_with_slot("skill-1");

    assert!(matches!(
        validate_engine_profile(&profile, true),
        Err(AppError::Config(_))
    ));
}

#[test]
fn test_engine_profile_validation_accepts_enabled_execution_for_start() {
    let mut profile = profile_with_slot("skill-1");
    profile.base.exec.enabled = true;

    assert!(validate_engine_profile(&profile, true).is_ok());
}

#[test]
fn test_engine_validation_rejects_invalid_expr_reference() {
    let mut profile = profile_with_slot("skill-1");
    profile.rotations[0].phases[0].skills[0].condition_expr = Some(serde_json::json!({
        "type": "pixel_point",
        "point_id": "missing",
        "tolerance": 10
    }));

    assert!(matches!(
        validate_profile_for_engine(&profile, false),
        Err(AppError::Config(_))
    ));
}

#[test]
fn test_preflight_report_rejects_empty_default_profile() {
    let profile = default_profile("default");

    let report = preflight_report_from_profile(&profile, false);

    assert!(!report.ready);
    assert!(!report.exec_enabled);
    assert_eq!(report.executable_slot_count, 0);
    assert!(report.error.is_some());
}

#[test]
fn test_preflight_report_accepts_enabled_executable_profile() {
    let mut profile = profile_with_slot("skill-1");
    profile.base.exec.enabled = true;

    let report = preflight_report_from_profile(&profile, false);

    assert!(report.ready);
    assert!(report.exec_enabled);
    assert_eq!(report.skill_count, 1);
    assert_eq!(report.executable_slot_count, 1);
    assert!(report.error.is_none());
}

#[test]
fn test_preflight_report_rejects_running_engine() {
    let mut profile = profile_with_slot("skill-1");
    profile.base.exec.enabled = true;

    let report = preflight_report_from_profile(&profile, true);

    assert!(!report.ready);
    assert_eq!(report.error.as_deref(), Some("engine already running"));
}

#[test]
fn test_attempt_config_uses_base_exec_values() {
    let mut profile = profile_with_slot("skill-1");
    profile.base.exec.default_skill_gap_ms = 77;
    profile.base.exec.poll_not_ready_ms = 88;
    profile.base.exec.max_retries = 2;
    profile.base.exec.retry_gap_ms = 33;
    profile.base.cast_bar.poll_interval_ms = 44;
    profile.base.cast_bar.max_wait_factor = 2.0;

    let cfg = attempt_config_from_base(&profile.base);

    assert_eq!(cfg.default_gap_ms, 77);
    assert_eq!(cfg.poll_not_ready_ms, 88);
    assert_eq!(cfg.max_retries, 2);
    assert_eq!(cfg.retry_gap_ms, 33);
    assert_eq!(cfg.complete_poll_ms, 44);
    assert_eq!(cfg.complete_max_wait_factor, 2.0);
}

#[test]
fn test_attempt_config_enables_roi_when_mode_is_roi() {
    let mut profile = profile_with_slot("skill-1");
    profile.base.cast_bar.mode = "roi".into();
    profile.base.cast_bar.roi.enabled = false;
    profile.base.cast_bar.roi.width = 320;
    profile.base.cast_bar.roi.height = 28;

    let cfg = attempt_config_from_base(&profile.base);

    let roi = cfg.cast_bar_roi.unwrap();
    assert!(roi.enabled);
    assert_eq!(roi.width, 320);
    assert_eq!(roi.height, 28);
}

#[test]
fn test_simulate_with_pixel_overrides_satisfies_point_condition() {
    let config = CycleConfig {
        name: "sim".into(),
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
                skill_id: "skill-1".into(),
                priority: 1,
                label: String::new(),
                slot_role: SkillSlotRole::Mandatory,
                readiness_expr: None,
                readiness_policy: Default::default(),
                condition_expr: Some(serde_json::json!({
                    "type": "pixel_point",
                    "point_id": "point-1",
                    "tolerance": 0
                })),
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
        }],
    };
    let skills = vec![test_skill("skill-1", "1", true)];
    let points = vec![Point {
        id: "point-1".into(),
        name: "point".into(),
        monitor: "primary".into(),
        vx: 10,
        vy: 20,
        color: ColorRGB { r: 1, g: 2, b: 3 },
        tolerance: 0,
        sample: SampleConfig {
            mode: "single".into(),
            radius: 0,
        },
        captured_at: String::new(),
        note: String::new(),
    }];
    let sampler = OverridePixelSampler::new(vec![PixelOverride {
        monitor: "primary".into(),
        x: 10,
        y: 20,
        r: 1,
        g: 2,
        b: 3,
    }]);

    let json = simulate_rotation_with_sampler(
        &config,
        &skills,
        &points,
        &sampler,
        SkillAttemptConfig::default(),
    )
    .unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    let events = value["events"].as_array().unwrap();

    assert!(!events.is_empty());
    assert_eq!(events[0]["skillId"], "skill-1");
}

#[test]
fn test_simulate_with_pixel_overrides_reports_condition_reason() {
    let config = CycleConfig {
        name: "sim".into(),
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
                skill_id: "skill-1".into(),
                priority: 1,
                label: String::new(),
                slot_role: SkillSlotRole::Mandatory,
                readiness_expr: None,
                readiness_policy: Default::default(),
                condition_expr: Some(serde_json::json!({
                    "type": "pixel_point",
                    "point_id": "point-1",
                    "tolerance": 0
                })),
                start_expr: None,
                complete_expr: None,
                override_cast_ms: None,
                protected_release: false,
                attempt_policy: None,
                post_actions: vec![],
            }],
        }],
    };
    let skills = vec![test_skill("skill-1", "1", true)];
    let points = vec![Point {
        id: "point-1".into(),
        name: "point".into(),
        monitor: "primary".into(),
        vx: 10,
        vy: 20,
        color: ColorRGB { r: 1, g: 2, b: 3 },
        tolerance: 0,
        sample: SampleConfig {
            mode: "single".into(),
            radius: 0,
        },
        captured_at: String::new(),
        note: String::new(),
    }];
    let sampler = OverridePixelSampler::new(vec![PixelOverride {
        monitor: "primary".into(),
        x: 10,
        y: 20,
        r: 9,
        g: 9,
        b: 9,
    }]);

    let json = simulate_rotation_with_sampler(
        &config,
        &skills,
        &points,
        &sampler,
        SkillAttemptConfig::default(),
    )
    .unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    let events = value["events"].as_array().unwrap();

    assert!(!events.is_empty());
    assert_eq!(events[0]["event"], "skip");
    assert_eq!(events[0]["outcome"], "NOT_READY");
    assert!(
        events[0]["reason"]
            .as_str()
            .is_some_and(|reason| reason.starts_with("condition_false:"))
    );
}

#[test]
fn test_simulate_profile_rotation_with_pixels_accepts_profile_content() {
    let mut profile = profile_with_slot("skill-1");
    profile.rotations[0].max_cycles = 1;
    let content = serde_json::to_string(&profile).unwrap();

    let json = simulate_profile_rotation_with_pixels(content, vec![]).unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    let events = value["events"].as_array().unwrap();

    assert!(!events.is_empty());
    assert_eq!(events[0]["skillId"], "skill-1");
}

#[test]
fn test_simulate_profile_rotation_rejects_empty_profile_content() {
    let profile = default_profile("default");
    let content = serde_json::to_string(&profile).unwrap();

    assert!(simulate_profile_rotation_with_pixels(content, vec![]).is_err());
}

#[test]
fn test_simulate_ipc_smoke_fixture_returns_event_counts() {
    let json = simulate_ipc_smoke_fixture().unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();

    assert_eq!(value["profile_id"], "ipc-smoke");
    assert!(
        value["direct_events"]
            .as_u64()
            .is_some_and(|count| count > 0)
    );
    assert!(
        value["pixel_events"]
            .as_u64()
            .is_some_and(|count| count > 0)
    );
}
