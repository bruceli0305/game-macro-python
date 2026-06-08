//! Profile TOML 持久化

use crate::error::{AppError, AppResult};
use crate::models::base::{
    BaseConfig, CaptureConfig, CastBarConfig, ExecConfig, IoConfig, PickConfig, UiConfig,
};
use crate::models::cycle::{CycleConfig, CyclePhase};
use crate::models::point::PointsFile;
use crate::models::profile::Profile;
use crate::models::profile::ProfileMeta;
use crate::models::skill::SkillsFile;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const PROFILE_FILE_NAME: &str = "profile.toml";

/// Profile 文件仓储 — TOML 格式
pub struct ProfileStore {
    root: PathBuf,
}

impl ProfileStore {
    pub fn new(root: PathBuf) -> Self {
        tracing::info!("ProfileStore 根目录: {}", root.display());
        Self { root }
    }

    pub fn list(&self) -> AppResult<Vec<String>> {
        let profiles_dir = self.root.join("profiles");
        if !profiles_dir.exists() {
            return Ok(vec![]);
        }
        let mut names = Vec::new();
        for entry in std::fs::read_dir(&profiles_dir)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                names.push(entry.file_name().to_string_lossy().to_string());
            }
        }
        Ok(names)
    }

    pub fn load(&self, name: &str) -> AppResult<Profile> {
        let path = self
            .root
            .join("profiles")
            .join(name)
            .join(PROFILE_FILE_NAME);
        if !path.exists() {
            return Err(AppError::Config(format!("Profile not found: {name}")));
        }
        let content = std::fs::read_to_string(&path)?;
        Ok(toml::from_str(&content)?)
    }

    pub fn load_or_create_default(&self, name: &str) -> AppResult<Profile> {
        match self.load(name) {
            Ok(profile) => Ok(profile),
            Err(AppError::Config(_)) => {
                let profile = default_profile(name);
                self.save(name, &profile)?;
                Ok(profile)
            }
            Err(error) => Err(error),
        }
    }

    pub fn save(&self, name: &str, profile: &Profile) -> AppResult<()> {
        let dir = self.root.join("profiles").join(name);
        std::fs::create_dir_all(&dir)?;

        let content = toml::to_string_pretty(profile)?;
        let path = dir.join(PROFILE_FILE_NAME);
        std::fs::write(&path, &content)?;

        tracing::info!("Profile '{name}' 已保存");
        Ok(())
    }
}

fn timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs().to_string())
        .unwrap_or_default()
}

pub fn default_profile(name: &str) -> Profile {
    let now = timestamp_string();
    Profile {
        schema_version: 1,
        meta: ProfileMeta {
            profile_id: name.into(),
            profile_name: name.into(),
            created_at: now.clone(),
            updated_at: now,
            description: String::new(),
        },
        base: BaseConfig {
            schema_version: 2,
            ui: UiConfig {
                theme: "darkly".into(),
            },
            capture: CaptureConfig {
                monitor_policy: "primary".into(),
            },
            pick: PickConfig {
                confirm_hotkey: "f8".into(),
                mouse_avoid: true,
                mouse_avoid_offset_y: 80,
                mouse_avoid_settle_ms: 80,
            },
            io: IoConfig {
                auto_save: true,
                backup_on_save: false,
            },
            cast_bar: CastBarConfig {
                mode: "timer".into(),
                point_id: String::new(),
                tolerance: 15,
                poll_interval_ms: 30,
                max_wait_factor: 1.5,
            },
            exec: ExecConfig {
                enabled: false,
                toggle_hotkey: String::new(),
                default_skill_gap_ms: 50,
                poll_not_ready_ms: 50,
                max_retries: 3,
                retry_gap_ms: 30,
            },
        },
        skills: SkillsFile {
            schema_version: 2,
            skills: vec![],
        },
        points: PointsFile {
            schema_version: 3,
            points: vec![],
        },
        rotations: vec![CycleConfig {
            name: "default".into(),
            phases: vec![CyclePhase {
                name: "Phase 1".into(),
                skills: vec![],
                complete_when: "any_fired".into(),
            }],
            poll_interval_ms: 100,
            max_cycles: 0,
        }],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_save_and_load() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());
        let profile = Profile::default();
        store.save("test", &profile).unwrap();
        assert!(
            tmp.path()
                .join("profiles")
                .join("test")
                .join("profile.toml")
                .exists()
        );
        assert!(
            !tmp.path()
                .join("profiles")
                .join("test")
                .join("profile.json")
                .exists()
        );
        let loaded = store.load("test").unwrap();
        assert_eq!(loaded.schema_version, profile.schema_version);
    }

    #[test]
    fn test_list_profiles() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());
        store.save("p1", &Profile::default()).unwrap();
        store.save("p2", &Profile::default()).unwrap();
        let names = store.list().unwrap();
        assert!(names.contains(&"p1".to_string()));
        assert!(names.contains(&"p2".to_string()));
    }

    #[test]
    fn test_load_invalid_toml_returns_typed_error() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("profiles").join("bad");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join(PROFILE_FILE_NAME), "schema_version = ").unwrap();

        let store = ProfileStore::new(tmp.path().to_path_buf());
        assert!(matches!(
            store.load("bad"),
            Err(AppError::TomlDeserialize(_))
        ));
    }

    #[test]
    fn test_load_or_create_default_persists_profile() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());

        let profile = store.load_or_create_default("default").unwrap();

        assert_eq!(profile.meta.profile_name, "default");
        assert_eq!(profile.rotations.len(), 1);
        assert!(
            tmp.path()
                .join("profiles")
                .join("default")
                .join("profile.toml")
                .exists()
        );
    }
}
