use super::*;
use crate::ast::evaluator::{CastBarRoiProvider, CastBarRoiState, PixelSampler};
use crate::models::cycle::{
    AssistInterruptPolicy, AssistLaneConfig, AttemptPolicy, CyclePhase, CycleStateSchema,
    ObserverActionSlot, ObserverLaneConfig, PhaseFallbackTransition, PhaseTransitionRule,
    ReadinessPolicy, RuntimeAction, RuntimeCounterDef, RuntimeMarkerDef, RuntimeTimerDef,
    SkillSlot, SkillSlotRole,
};
use crate::models::skill::{AmmoStagePixel, ColorRGB, PixelSpec, SampleConfig, Skill};
use serde_json::json;

struct DummySampler {
    rgb: (u8, u8, u8),
}
impl PixelSampler for DummySampler {
    fn sample_rgb_abs(
        &self,
        _m: &str,
        _x: i32,
        _y: i32,
        _mode: &str,
        _r: u8,
    ) -> Option<(u8, u8, u8)> {
        Some(self.rgb)
    }
}

struct DummyKeySender {
    keys: Vec<String>,
    fail: bool,
}
impl KeySender for DummyKeySender {
    fn send_key(&mut self, key: &str) -> bool {
        self.keys.push(key.into());
        !self.fail
    }
}

struct DummyCastBarRoiProvider {
    state: Option<CastBarRoiState>,
}

impl CastBarRoiProvider for DummyCastBarRoiProvider {
    fn get_cast_bar_roi_state(&self) -> Option<CastBarRoiState> {
        self.state
    }
}

fn make_skill(id: &str, key: &str) -> Skill {
    Skill {
        id: id.into(),
        name: id.into(),
        enabled: true,
        trigger_key: key.into(),
        cast: Default::default(),
        pixel: PixelSpec {
            monitor: "primary".into(),
            vx: 0,
            vy: 0,
            color: ColorRGB {
                r: 100,
                g: 150,
                b: 200,
            },
            tolerance: 10,
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

fn make_slot(skill_id: &str, priority: u32) -> SkillSlot {
    SkillSlot {
        skill_id: skill_id.into(),
        priority,
        label: String::new(),
        slot_role: SkillSlotRole::Mandatory,
        condition_expr: None,
        readiness_expr: None,
        readiness_policy: ReadinessPolicy::Required,
        start_expr: None,
        complete_expr: None,
        override_cast_ms: None,
        protected_release: false,
        attempt_policy: None,
        post_actions: vec![],
    }
}

fn make_assist_lane(policy: AssistInterruptPolicy, skills: Vec<SkillSlot>) -> AssistLaneConfig {
    AssistLaneConfig {
        id: "assist".into(),
        name: "Assist".into(),
        enabled: true,
        check_interval_ms: 50,
        interrupt_policy: policy,
        skills,
    }
}

#[test]
fn test_empty_config_no_panic() {
    let config = CycleConfig::default();
    let points = vec![];
    let skills = vec![];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };
    let acted = exec.tick(&mut ks, &|| false, 0);
    assert!(!acted);
}

#[test]
fn test_precompiled_expr_cache_covers_phase_observer_assist_and_transition() {
    let mut main_slot = make_slot("sk1", 1);
    main_slot.condition_expr = Some(json!({"type": "const", "value": true}));
    main_slot.start_expr = Some(json!({"type": "const", "value": true}));
    main_slot.complete_expr = Some(json!({"type": "const", "value": true}));

    let mut assist_slot = make_slot("sk2", 1);
    assist_slot.condition_expr = Some(json!({"type": "const", "value": true}));

    let observer_slot = ObserverActionSlot {
        id: "watch_cast".into(),
        label: "Watch cast".into(),
        priority: 1,
        condition_expr: Some(json!({"type": "const", "value": true})),
        actions: vec![RuntimeAction::RecordTimer {
            timer_id: "cast_seen".into(),
        }],
    };

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![main_slot],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![PhaseTransitionRule {
                label: "jump".into(),
                condition_expr: Some(json!({"type": "const", "value": true})),
                target_phase: "P1".into(),
            }],
            fallback_transition: None,
        }],
        observer_lanes: vec![ObserverLaneConfig {
            id: "observer".into(),
            name: "Observer".into(),
            enabled: true,
            check_interval_ms: 50,
            actions: vec![observer_slot],
        }],
        assist_lanes: vec![make_assist_lane(
            AssistInterruptPolicy::IdleOnly,
            vec![assist_slot],
        )],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
    let sampler = DummySampler { rgb: (0, 0, 0) };

    let exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );

    assert_eq!(exec.slot_expr_cache.len(), 2);
    assert_eq!(exec.transition_rule_expr_cache.len(), 1);
    let main_exprs = exec
        .slot_expr_cache
        .get(&SlotExprKey::Phase {
            phase_index: 0,
            slot_index: 0,
        })
        .expect("main slot expressions cached");
    assert!(main_exprs.condition_expr.is_some());
    assert!(main_exprs.start_expr.is_some());
    assert!(main_exprs.complete_expr.is_some());
    let assist_exprs = exec
        .slot_expr_cache
        .get(&SlotExprKey::Assist {
            lane_index: 0,
            slot_index: 0,
        })
        .expect("assist slot expressions cached");
    assert!(assist_exprs.condition_expr.is_some());
    let observer_expr = exec
        .observer_action_expr_cache
        .get(&ObserverActionExprKey {
            lane_index: 0,
            action_index: 0,
        })
        .expect("observer action expression cached");
    assert!(observer_expr.is_some());
}

#[test]
fn test_precompiled_expr_cache_keys_survive_config_clone() {
    let mut slot = make_slot("sk1", 1);
    slot.condition_expr = Some(json!({"type": "const", "value": false}));
    let config = CycleConfig {
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
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let cloned = config.clone();
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );

    let (ready, reason) = exec.check_skill_ready_at(
        &cloned.phases[0].skills[0],
        SlotExprKey::Phase {
            phase_index: 0,
            slot_index: 0,
        },
        0,
    );

    assert!(!ready);
    assert!(reason.starts_with("condition_false:"));
}

#[test]
fn test_observer_action_records_timer_without_sending_key() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![],
        observer_lanes: vec![ObserverLaneConfig {
            id: "observer".into(),
            name: "Observer".into(),
            enabled: true,
            check_interval_ms: 50,
            actions: vec![ObserverActionSlot {
                id: "cast_seen".into(),
                label: "Cast seen".into(),
                priority: 1,
                condition_expr: Some(json!({"type": "const", "value": true})),
                actions: vec![RuntimeAction::RecordTimer {
                    timer_id: "cast_timer".into(),
                }],
            }],
        }],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![],
            timers: vec![RuntimeTimerDef {
                id: "cast_timer".into(),
                name: "Cast timer".into(),
                reset_on_cycle_start: false,
            }],
            counters: vec![],
        }),
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(!exec.tick(&mut ks, &|| false, 25));
    assert!(ks.keys.is_empty());
    assert_eq!(exec.runtime.timers.get("cast_timer"), Some(&25));
    assert!(
        exec.log
            .iter()
            .any(|entry| entry.event == "observer_action")
    );
}

#[test]
fn test_observer_action_gates_main_skill_in_same_tick() {
    let mut slot = make_slot("sk1", 1);
    slot.condition_expr = Some(json!({
        "type": "marker_eq",
        "marker_id": "cast_state",
        "value": "active"
    }));
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![slot],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![ObserverLaneConfig {
            id: "observer".into(),
            name: "Observer".into(),
            enabled: true,
            check_interval_ms: 50,
            actions: vec![ObserverActionSlot {
                id: "mark_cast".into(),
                label: "Mark cast".into(),
                priority: 1,
                condition_expr: Some(json!({"type": "const", "value": true})),
                actions: vec![RuntimeAction::SetMarker {
                    marker_id: "cast_state".into(),
                    value: "active".into(),
                }],
            }],
        }],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![RuntimeMarkerDef {
                id: "cast_state".into(),
                name: "Cast state".into(),
                initial_value: "idle".into(),
                allowed_values: vec!["idle".into(), "active".into()],
            }],
            timers: vec![],
            counters: vec![],
        }),
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(
        exec.runtime.markers.get("cast_state"),
        Some(&"active".to_string())
    );
    assert_eq!(ks.keys, vec!["f1"]);
}

#[test]
fn test_observer_lane_interval_prevents_repeated_counter_updates() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![],
        observer_lanes: vec![ObserverLaneConfig {
            id: "observer".into(),
            name: "Observer".into(),
            enabled: true,
            check_interval_ms: 100,
            actions: vec![ObserverActionSlot {
                id: "count_cast".into(),
                label: "Count cast".into(),
                priority: 1,
                condition_expr: Some(json!({"type": "const", "value": true})),
                actions: vec![RuntimeAction::IncrementCounter {
                    counter_id: "seen_count".into(),
                    by: 1,
                }],
            }],
        }],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![],
            timers: vec![],
            counters: vec![RuntimeCounterDef {
                id: "seen_count".into(),
                name: "Seen count".into(),
                initial_value: 0,
                reset_on_phase_entry: false,
                reset_on_cycle_start: false,
            }],
        }),
    };
    let points = vec![];
    let skills = vec![];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(!exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.runtime.counters.get("seen_count"), Some(&1));
    assert!(!exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.runtime.counters.get("seen_count"), Some(&1));
    assert!(!exec.tick(&mut ks, &|| false, 100));
    assert_eq!(exec.runtime.counters.get("seen_count"), Some(&2));
    assert!(ks.keys.is_empty());
}

#[test]
fn test_precompiled_slot_exprs_keep_duplicate_skill_slots_distinct() {
    let mut blocked_slot = make_slot("sk1", 1);
    blocked_slot.condition_expr = Some(json!({"type": "const", "value": false}));
    let mut ready_slot = make_slot("sk1", 2);
    ready_slot.condition_expr = Some(json!({"type": "const", "value": true}));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![blocked_slot, ready_slot],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert_eq!(exec.slot_expr_cache.len(), 2);
    let acted = exec.tick(&mut ks, &|| false, 0);

    assert!(acted);
    assert_eq!(ks.keys, vec!["f1"]);
}

#[test]
fn test_assist_lane_executes_when_main_has_no_ready_slot() {
    let config = CycleConfig {
        name: "assist_idle".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![SkillSlot {
                condition_expr: Some(json!({ "type": "const", "value": false })),
                ..make_slot("main", 1)
            }],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![make_assist_lane(
            AssistInterruptPolicy::IdleOnly,
            vec![make_slot("assist", 1)],
        )],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("main", "M"), make_skill("assist", "A")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));

    assert_eq!(ks.keys, vec!["A"]);
    assert!(exec.log.iter().any(|entry| entry.event == "assist_execute"
        && entry.skill_id == "assist"
        && entry.phase_name == "assist:Assist"));
    assert!(!exec.state.fired_in_phase.contains("assist"));
}

#[test]
fn test_assist_idle_only_does_not_interrupt_main_complete_wait() {
    let mut main_skill = make_skill("main", "M");
    main_skill.cast.readbar_ms = 100;
    let config = CycleConfig {
        name: "assist_no_interrupt".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("main", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![make_assist_lane(
            AssistInterruptPolicy::IdleOnly,
            vec![make_slot("assist", 1)],
        )],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![main_skill, make_skill("assist", "A")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert!(!exec.tick(&mut ks, &|| false, 10));

    assert_eq!(ks.keys, vec!["M"]);
    assert!(!exec.log.iter().any(|entry| entry.event == "assist_execute"));
}

#[test]
fn test_assist_complete_wait_can_run_during_main_complete_wait() {
    let mut main_skill = make_skill("main", "M");
    main_skill.cast.readbar_ms = 100;
    let config = CycleConfig {
        name: "assist_complete_wait".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("main", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![make_assist_lane(
            AssistInterruptPolicy::CompleteWait,
            vec![make_slot("assist", 1)],
        )],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![main_skill, make_skill("assist", "A")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert!(exec.tick(&mut ks, &|| false, 10));
    assert!(exec.tick(&mut ks, &|| false, 100));

    assert_eq!(ks.keys, vec!["M", "A"]);
    assert_eq!(exec.state.total_executed, 2);
    assert!(
        exec.log
            .iter()
            .any(|entry| entry.event == "assist_execute" && entry.skill_id == "assist")
    );
    assert!(exec.log.iter().any(|entry| entry.event == "execute"
        && entry.skill_id == "main"
        && entry.outcome == "Success"));
}

#[test]
fn test_protected_release_blocks_assist_complete_wait_interrupt() {
    let mut main_skill = make_skill("main", "M");
    main_skill.cast.readbar_ms = 100;
    let mut main_slot = make_slot("main", 1);
    main_slot.protected_release = true;
    let config = CycleConfig {
        name: "assist_protected".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![main_slot],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![make_assist_lane(
            AssistInterruptPolicy::CompleteWait,
            vec![make_slot("assist", 1)],
        )],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![main_skill, make_skill("assist", "A")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert!(!exec.tick(&mut ks, &|| false, 10));
    assert!(exec.tick(&mut ks, &|| false, 100));

    assert_eq!(ks.keys, vec!["M"]);
    assert_eq!(exec.state.total_executed, 1);
    assert!(!exec.log.iter().any(|entry| entry.event == "assist_execute"));
}

#[test]
fn test_single_phase_single_skill() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    // tick 1: execute sk1; any_fired completes the phase and resets the cycle.
    let acted = exec.tick(&mut ks, &|| false, 0);
    assert!(acted);
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.cycle_count, 1);
    assert_eq!(exec.state.next_ready_ms, 50);
    assert_eq!(ks.keys, vec!["f1"]);

    // tick 2: the default post-attempt gap blocks immediate re-fire.
    let acted = exec.tick(&mut ks, &|| false, 1);
    assert!(!acted);
    assert_eq!(exec.state.total_executed, 1);

    // tick 3: new cycle phase 0, sk1 is due again after the gap.
    let acted = exec.tick(&mut ks, &|| false, 50);
    assert!(acted);
    assert_eq!(exec.state.total_executed, 2);
    assert_eq!(exec.state.cycle_count, 2);
}

#[test]
fn test_priority_order() {
    // Lower priority number executes first.
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("skB", 2), make_slot("skA", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("skA", "A"), make_skill("skB", "B")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    // tick 1: the executor should pick skA first because it has priority 1.
    let acted = exec.tick(&mut ks, &|| false, 0);
    assert!(acted);
    assert_eq!(ks.keys, vec!["A"]);
}

#[test]
fn test_stopped() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    let acted = exec.tick(&mut ks, &|| true, 0);
    assert!(!acted);
}

#[test]
fn test_condition_expr_blocks_skill() {
    // condition false means the skill is not ready.
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![SkillSlot {
                skill_id: "sk1".into(),
                priority: 1,
                label: String::new(),
                slot_role: SkillSlotRole::Mandatory,
                readiness_expr: None,
                readiness_policy: Default::default(),
                condition_expr: Some(json!({"type": "const", "value": false})),
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
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    let acted = exec.tick(&mut ks, &|| false, 0);
    assert!(!acted);
}

#[test]
fn test_advisory_readiness_allows_attempt_when_signal_is_false() {
    let mut slot = make_slot("sk1", 1);
    slot.condition_expr = Some(json!({"type": "const", "value": true}));
    slot.readiness_expr = Some(json!({
        "type": "pixel_skill_not_black",
        "skill_id": "sk1",
        "tolerance": 64
    }));
    slot.readiness_policy = ReadinessPolicy::Advisory;
    let config = CycleConfig {
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
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "C")];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    let (ready, reason) = exec.check_skill_ready_at(
        &config.phases[0].skills[0],
        SlotExprKey::Phase {
            phase_index: 0,
            slot_index: 0,
        },
        0,
    );
    assert!(ready);
    assert!(reason.starts_with("condition_true readiness_advisory:"));

    let acted = exec.tick(&mut ks, &|| false, 0);

    assert!(acted);
    assert_eq!(ks.keys, vec!["C"]);
}

#[test]
fn test_required_readiness_blocks_attempt_when_signal_is_false() {
    let mut slot = make_slot("sk1", 1);
    slot.condition_expr = Some(json!({"type": "const", "value": true}));
    slot.readiness_expr = Some(json!({
        "type": "pixel_skill_not_black",
        "skill_id": "sk1",
        "tolerance": 64
    }));
    slot.readiness_policy = ReadinessPolicy::Required;
    let config = CycleConfig {
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
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "C")];
    let sampler = DummySampler { rgb: (0, 0, 0) };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    let (ready, reason) = exec.check_skill_ready_at(
        &config.phases[0].skills[0],
        SlotExprKey::Phase {
            phase_index: 0,
            slot_index: 0,
        },
        0,
    );
    assert!(!ready);
    assert!(reason.starts_with("readiness_false:"));

    let acted = exec.tick(&mut ks, &|| false, 0);

    assert!(!acted);
    assert!(ks.keys.is_empty());
    assert!(exec.log.iter().any(|entry| {
        entry.skill_id == "sk1"
            && entry.event == "skip"
            && entry.reason.starts_with("readiness_false:")
    }));
}

#[test]
fn test_none_ready_phase_advances_when_all_slots_are_already_not_ready() {
    let mut first = make_slot("sk1", 1);
    first.condition_expr = Some(json!({"type": "const", "value": false}));
    let mut second = make_slot("sk2", 2);
    second.condition_expr = Some(json!({"type": "const", "value": false}));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![first, second],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![make_slot("sk3", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![
        make_skill("sk1", "A"),
        make_skill("sk2", "B"),
        make_skill("sk3", "C"),
    ];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    let acted = exec.tick(&mut ks, &|| false, 0);
    assert!(acted);
    assert!(ks.keys.is_empty());
    assert_eq!(exec.state.phase_index, 1);
}

#[test]
fn test_reacquire_prefers_stable_loop_phase_anchor() {
    let mut opener_slot = make_slot("sk1", 1);
    opener_slot.complete_expr = Some(json!({"type": "const", "value": true}));
    let mut loop_slot = make_slot("sk2", 1);
    loop_slot.complete_expr = Some(json!({"type": "const", "value": true}));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "Preparation - Fire".into(),
                skills: vec![opener_slot],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "Loop - Fire".into(),
                skills: vec![loop_slot],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "A"), make_skill("sk2", "B")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );

    assert_eq!(exec.reacquire_phase_from_current_frame(0), Some(1));
    assert_eq!(exec.state.phase_index, 1);
}

#[test]
fn test_reacquire_transition_rule_wins_over_phase_anchor() {
    let mut opener_slot = make_slot("sk1", 1);
    opener_slot.complete_expr = Some(json!({"type": "const", "value": true}));
    let mut loop_slot = make_slot("sk2", 1);
    loop_slot.complete_expr = Some(json!({"type": "const", "value": true}));
    let burst_slot = make_slot("sk3", 1);

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "Loop - Earth".into(),
                skills: vec![loop_slot],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![PhaseTransitionRule {
                    label: "burst ready".into(),
                    condition_expr: Some(json!({"type": "const", "value": true})),
                    target_phase: "Burst opener".into(),
                }],
                fallback_transition: None,
            },
            CyclePhase {
                name: "Preparation - Earth".into(),
                skills: vec![opener_slot],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "Burst opener".into(),
                skills: vec![burst_slot],
                complete_when: "none_ready".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![
        make_skill("sk1", "A"),
        make_skill("sk2", "B"),
        make_skill("sk3", "C"),
    ];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );

    assert_eq!(exec.reacquire_phase_from_current_frame(0), Some(2));
    assert_eq!(exec.state.phase_index, 2);
}

#[test]
fn test_all_fired_completion() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("skA", 1), make_slot("skB", 2)],
                complete_when: "all_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![make_slot("skC", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![
        make_skill("skA", "A"),
        make_skill("skB", "B"),
        make_skill("skC", "C"),
    ];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    // tick 1: skA (priority 1)
    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.phase_index, 0); // Still in P1 because all_fired is not complete.

    // tick 2: skB (priority 2, skA has already fired).
    assert!(exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.state.phase_index, 1); // P1 completes and advances to P2.

    // tick 3: skC (P2)
    assert!(exec.tick(&mut ks, &|| false, 100));
    // P2 completes and the cycle resets to P1.
    assert_eq!(exec.state.cycle_count, 1);
}

#[test]
fn test_filler_slot_does_not_block_mandatory_phase_completion() {
    let mut filler = make_slot("fill", 2);
    filler.slot_role = SkillSlotRole::Filler;
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("main", 1), filler],
            complete_when: "all_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("main", "M"), make_skill("fill", "F")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(ks.keys, vec!["M"]);
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.cycle_count, 1);
    assert!(!exec.state.fired_in_cycle.contains("fill"));
}

#[test]
fn test_priority_slot_does_not_complete_phase_before_mandatory_slot() {
    let mut priority = make_slot("priority", 1);
    priority.slot_role = SkillSlotRole::Priority;
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![priority, make_slot("main", 2)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![make_slot("next", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![
        make_skill("priority", "P"),
        make_skill("main", "M"),
        make_skill("next", "N"),
    ];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(ks.keys, vec!["P"]);
    assert_eq!(exec.state.phase_index, 0);
    assert!(exec.state.fired_in_phase.contains("priority"));

    assert!(exec.tick(&mut ks, &|| false, 50));
    assert_eq!(ks.keys, vec!["P", "M"]);
    assert_eq!(exec.state.phase_index, 1);
}

#[test]
fn test_runtime_metrics_after_success() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.node_exec, 1);
    assert_eq!(runtime.attempt_started, 1);
    assert_eq!(runtime.key_sent_ok, 1);
    assert_eq!(runtime.cast_started, 1);
    assert_eq!(runtime.success, 1);
    assert_eq!(runtime.fail, 0);
}

#[test]
fn test_assume_success_waits_readbar_across_ticks() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.cast.readbar_ms = 100;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 0);
    assert_eq!(exec.state.next_ready_ms, 100);
    assert!(exec.pending_attempt.is_some());
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.key_sent_ok, 1);
    assert_eq!(runtime.cast_started, 1);
    assert_eq!(runtime.success, 0);

    assert!(!exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.state.total_executed, 0);

    assert!(exec.tick(&mut ks, &|| false, 100));
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.next_ready_ms, 150);
    assert!(exec.pending_attempt.is_none());
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.success, 1);
}

#[test]
fn test_start_expr_waits_until_timeout() {
    let mut slot = make_slot("sk1", 1);
    slot.start_expr = Some(json!({"type": "const", "value": false}));
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let cfg = SkillAttemptConfig {
        max_retries: 0,
        start_timeout_ms: 20,
        start_poll_ms: 10,
        ..Default::default()
    };
    let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 0);
    assert_eq!(exec.state.next_ready_ms, 10);
    assert!(exec.pending_attempt.is_some());

    assert!(!exec.tick(&mut ks, &|| false, 10));
    assert_eq!(exec.state.total_executed, 0);
    assert_eq!(exec.state.next_ready_ms, 20);

    assert!(exec.tick(&mut ks, &|| false, 20));
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.last_outcome, "Failed");
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.key_sent_ok, 1);
    assert_eq!(runtime.cast_started, 0);
    assert_eq!(runtime.fail, 1);
    assert_eq!(runtime.fail_by_reason.get("no_cast_start"), Some(&1));
}

#[test]
fn test_start_expr_accepts_cast_bar_roi_changed() {
    let mut slot = make_slot("sk1", 1);
    slot.start_expr = Some(json!({"type": "cast_bar_roi_changed"}));
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let roi = DummyCastBarRoiProvider {
        state: Some(CastBarRoiState {
            changed_from_baseline: true,
            border_visible: false,
            gone: false,
            changed_ratio: 0.4,
            border_match_ratio: 0.0,
        }),
    };
    let cfg = SkillAttemptConfig {
        max_retries: 0,
        start_timeout_ms: 20,
        start_poll_ms: 10,
        ..Default::default()
    };
    let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg)
        .with_cast_bar_roi_provider(Some(&roi));
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(ks.keys, vec!["f1"]);
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.cast_started, 1);
    assert_eq!(runtime.fail, 0);
}

#[test]
fn test_slot_attempt_policy_max_attempts_one_sends_one_key() {
    let mut slot = make_slot("sk1", 1);
    slot.start_expr = Some(json!({"type": "const", "value": false}));
    slot.attempt_policy = Some(AttemptPolicy {
        max_attempts: 1,
        start_timeout_ms: 20,
        complete_timeout_ms: 0,
        retry_delay_ms: 5,
        failure_policy: "next_slot".into(),
        complete_fallback: "assume_success_after_timeout".into(),
    });
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let cfg = SkillAttemptConfig {
        max_retries: 10,
        start_timeout_ms: 1000,
        start_poll_ms: 10,
        ..Default::default()
    };
    let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(ks.keys, vec!["f1"]);
    assert!(!exec.tick(&mut ks, &|| false, 10));
    assert_eq!(ks.keys, vec!["f1"]);
    assert!(exec.tick(&mut ks, &|| false, 20));
    assert_eq!(ks.keys, vec!["f1"]);
    assert_eq!(exec.state.last_outcome, "Failed");
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.key_sent_ok, 1);
    assert_eq!(runtime.fail_by_reason.get("no_cast_start"), Some(&1));
}

#[test]
fn test_slot_attempt_policy_complete_timeout_overrides_readbar() {
    let mut slot = make_slot("sk1", 1);
    slot.complete_expr = Some(json!({"type": "const", "value": false}));
    slot.attempt_policy = Some(AttemptPolicy {
        max_attempts: 1,
        start_timeout_ms: 20,
        complete_timeout_ms: 25,
        retry_delay_ms: 0,
        failure_policy: "next_slot".into(),
        complete_fallback: "fail".into(),
    });
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.cast.readbar_ms = 1000;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.next_ready_ms, 25);
    assert_eq!(exec.state.total_executed, 0);
    assert!(exec.tick(&mut ks, &|| false, 25));
    assert_eq!(exec.state.last_outcome, "Failed");
    assert_eq!(exec.state.next_ready_ms, 75);
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.key_sent_ok, 1);
    assert_eq!(runtime.fail_by_reason.get("timeout"), Some(&1));
}

#[test]
fn test_timer_post_action_gates_next_phase_skill() {
    let mut first = make_slot("sk1", 1);
    first.post_actions = vec![RuntimeAction::RecordTimer {
        timer_id: "burst".into(),
    }];

    let mut second = make_slot("sk2", 1);
    second.condition_expr = Some(json!({
        "type": "timer_elapsed_ge",
        "timer_id": "burst",
        "ms": 100
    }));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![first],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![second],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![],
            timers: vec![RuntimeTimerDef {
                id: "burst".into(),
                name: "Burst timer".into(),
                reset_on_cycle_start: false,
            }],
            counters: vec![],
        }),
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(ks.keys, vec!["f1"]);
    assert_eq!(exec.runtime.timers.get("burst"), Some(&0));
    assert_eq!(exec.state.phase_index, 1);

    assert!(!exec.tick(&mut ks, &|| false, 50));
    assert_eq!(ks.keys, vec!["f1"]);

    assert!(exec.tick(&mut ks, &|| false, 100));
    assert_eq!(ks.keys, vec!["f1", "f2"]);
}

#[test]
fn test_marker_post_action_gates_next_phase_skill() {
    let mut first = make_slot("sk1", 1);
    first.post_actions = vec![RuntimeAction::SetMarker {
        marker_id: "weapon".into(),
        value: "alt".into(),
    }];

    let mut second = make_slot("sk2", 1);
    second.condition_expr = Some(json!({
        "type": "marker_eq",
        "marker_id": "weapon",
        "value": "alt"
    }));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![first],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![second],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![RuntimeMarkerDef {
                id: "weapon".into(),
                name: "Weapon".into(),
                initial_value: "main".into(),
                allowed_values: vec!["main".into(), "alt".into()],
            }],
            timers: vec![],
            counters: vec![],
        }),
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert_eq!(exec.runtime.marker("weapon"), Some("main"));
    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.runtime.marker("weapon"), Some("alt"));
    assert_eq!(exec.state.phase_index, 1);
    assert!(exec.tick(&mut ks, &|| false, 50));
    assert_eq!(ks.keys, vec!["f1", "f2"]);
}

#[test]
fn test_counter_post_action_gates_next_phase_skill() {
    let mut first = make_slot("sk1", 1);
    first.post_actions = vec![RuntimeAction::IncrementCounter {
        counter_id: "main_wp2_count".into(),
        by: 1,
    }];

    let mut second = make_slot("sk2", 1);
    second.condition_expr = Some(json!({
        "type": "counter_ge",
        "counter_id": "main_wp2_count",
        "value": 1
    }));

    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![first],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![second],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: Some(CycleStateSchema {
            markers: vec![],
            timers: vec![],
            counters: vec![RuntimeCounterDef {
                id: "main_wp2_count".into(),
                name: "Main WP2 Count".into(),
                initial_value: 0,
                reset_on_phase_entry: false,
                reset_on_cycle_start: true,
            }],
        }),
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1"), make_skill("sk2", "f2")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert_eq!(exec.runtime.counter("main_wp2_count"), Some(0));
    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.runtime.counter("main_wp2_count"), Some(1));
    assert_eq!(exec.state.phase_index, 1);
    assert!(exec.tick(&mut ks, &|| false, 50));
    assert_eq!(ks.keys, vec!["f1", "f2"]);
}

#[test]
fn test_phase_transition_rule_jumps_to_named_phase() {
    let config = CycleConfig {
        name: "transition".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![PhaseTransitionRule {
                    label: "jump".into(),
                    condition_expr: Some(json!({"type": "const", "value": true})),
                    target_phase: "P3".into(),
                }],
                fallback_transition: Some(PhaseFallbackTransition::Next),
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![make_slot("sk2", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P3".into(),
                skills: vec![make_slot("sk3", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 100,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![
        make_skill("sk1", "f1"),
        make_skill("sk2", "f2"),
        make_skill("sk3", "f3"),
    ];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.phase_index, 2);
    assert!(
        exec.log
            .iter()
            .any(|entry| entry.event == "phase_transition" && entry.reason == "rule:jump->P3")
    );
    assert!(exec.tick(&mut ks, &|| false, 1_000));
    assert_eq!(ks.keys, vec!["f1", "f3"]);
}

#[test]
fn test_complete_expr_require_signal_times_out() {
    let mut slot = make_slot("sk1", 1);
    slot.complete_expr = Some(json!({"type": "const", "value": false}));
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.cast.readbar_ms = 100;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let cfg = SkillAttemptConfig {
        complete_policy: CompletePolicy::RequireSignal,
        complete_poll_ms: 25,
        complete_max_wait_factor: 1.0,
        ..Default::default()
    };
    let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 0);
    assert_eq!(exec.state.next_ready_ms, 25);
    assert!(exec.pending_attempt.is_some());

    assert!(!exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.state.total_executed, 0);

    assert!(exec.tick(&mut ks, &|| false, 100));
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.last_outcome, "Failed");
    assert_eq!(exec.state.next_ready_ms, 150);
    assert!(exec.pending_attempt.is_none());
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.cast_started, 1);
    assert_eq!(runtime.success, 0);
    assert_eq!(runtime.fail, 1);
    assert_eq!(runtime.fail_by_reason.get("timeout"), Some(&1));
}

#[test]
fn test_complete_expr_require_signal_succeeds() {
    let mut slot = make_slot("sk1", 1);
    slot.complete_expr = Some(json!({"type": "const", "value": true}));
    let config = CycleConfig {
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
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.cast.readbar_ms = 100;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let cfg = SkillAttemptConfig {
        complete_policy: CompletePolicy::RequireSignal,
        ..Default::default()
    };
    let mut exec = CycleExecutor::new(&config, &points, &skills, &sampler, cfg);
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 1);
    assert_eq!(exec.state.last_outcome, "Success");
    assert_eq!(exec.state.next_ready_ms, 50);
    assert!(exec.pending_attempt.is_none());
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.cast_started, 1);
    assert_eq!(runtime.success, 1);
    assert_eq!(runtime.fail, 0);
}

#[test]
fn test_runtime_metrics_after_not_ready() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![SkillSlot {
                skill_id: "sk1".into(),
                priority: 1,
                label: String::new(),
                slot_role: SkillSlotRole::Mandatory,
                readiness_expr: None,
                readiness_policy: Default::default(),
                condition_expr: Some(json!({"type": "const", "value": false})),
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
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 50,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let skills = vec![make_skill("sk1", "f1")];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(!exec.tick(&mut ks, &|| false, 0));
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.node_exec, 1);
    assert_eq!(runtime.ready_false, 1);
    assert_eq!(runtime.attempt_started, 0);
    assert_eq!(runtime.success, 0);
}

#[test]
fn test_skill_cooldown_blocks_until_due() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "always".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.cooldown_ms = 100;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 1);
    assert!(!exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.state.total_executed, 1);
    assert!(exec.tick(&mut ks, &|| false, 100));
    assert_eq!(exec.state.total_executed, 2);
}

#[test]
fn test_all_fired_respects_shots_per_cycle() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "all_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.shots_per_cycle = 2;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.phase_index, 0);
    assert_eq!(exec.state.cycle_count, 0);
    assert!(exec.tick(&mut ks, &|| false, 50));
    assert_eq!(exec.state.cycle_count, 1);
    assert_eq!(exec.state.total_executed, 2);
}

#[test]
fn test_zero_shots_per_cycle_allows_repeating_loop_skill() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![
            CyclePhase {
                name: "P1".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            },
            CyclePhase {
                name: "P2".into(),
                skills: vec![make_slot("sk1", 1)],
                complete_when: "any_fired".into(),
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: Some(PhaseFallbackTransition::Phase {
                    target_phase: "P1".into(),
                }),
            },
        ],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.shots_per_cycle = 0;
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(exec.tick(&mut ks, &|| false, 0));
    assert!(exec.tick(&mut ks, &|| false, 50));
    assert!(exec.tick(&mut ks, &|| false, 100));
    assert_eq!(exec.state.cycle_count, 0);
    assert_eq!(exec.state.total_executed, 3);
    assert_eq!(ks.keys, vec!["f1", "f1", "f1"]);
}

#[test]
fn test_ammo_stage_pixel_blocks_when_no_charge_matches() {
    let config = CycleConfig {
        name: "test".into(),
        phases: vec![CyclePhase {
            name: "P1".into(),
            skills: vec![make_slot("sk1", 1)],
            complete_when: "any_fired".into(),
            entry_actions: vec![],
            transition_rules: vec![],
            fallback_transition: None,
        }],
        observer_lanes: vec![],
        assist_lanes: vec![],
        poll_interval_ms: 10,
        max_cycles: 0,
        state_schema: None,
    };
    let points = vec![];
    let mut skill = make_skill("sk1", "f1");
    skill.ammo_stages = vec![AmmoStagePixel {
        charges_left: 1,
        pixel: PixelSpec {
            monitor: "primary".into(),
            vx: 0,
            vy: 0,
            color: ColorRGB { r: 1, g: 2, b: 3 },
            tolerance: 0,
            sample: SampleConfig {
                mode: "single".into(),
                radius: 0,
            },
        },
    }];
    let skills = vec![skill];
    let sampler = DummySampler {
        rgb: (100, 150, 200),
    };
    let mut exec = CycleExecutor::new(
        &config,
        &points,
        &skills,
        &sampler,
        SkillAttemptConfig::default(),
    );
    let mut ks = DummyKeySender {
        keys: vec![],
        fail: false,
    };

    assert!(!exec.tick(&mut ks, &|| false, 0));
    assert_eq!(exec.state.total_executed, 0);
    let runtime = exec.runtime.skills.get("sk1").unwrap();
    assert_eq!(runtime.ready_false, 1);
}
