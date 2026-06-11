//! Profile TOML persistence.

use crate::error::{AppError, AppResult};
use crate::models::base::{
    BaseConfig, CaptureConfig, CastBarConfig, CastBarRoiConfig, ExecConfig, IoConfig, PickConfig,
    UiConfig,
};
use crate::models::cycle::{CycleConfig, CyclePhase};
use crate::models::point::PointsFile;
use crate::models::profile::{Profile, ProfileMeta};
use crate::models::skill::SkillsFile;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const PROFILE_FILE_NAME: &str = "profile.toml";
const SETTINGS_FILE_NAME: &str = "settings.toml";
const DEFAULT_PROFILE_NAME: &str = "default";

/// Returns the application data directory used for persisted profiles.
pub fn app_data_dir() -> AppResult<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        let local = std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."));
        Ok(local.join("game-macro-tauri"))
    }

    #[cfg(target_os = "macos")]
    {
        let home = std::env::var("HOME")
            .map(PathBuf::from)
            .map_err(|_| AppError::Config("unable to determine home directory".into()))?;
        Ok(home
            .join("Library")
            .join("Application Support")
            .join("game-macro-tauri"))
    }

    #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
    {
        if let Ok(xdg_data_home) = std::env::var("XDG_DATA_HOME") {
            let trimmed = xdg_data_home.trim();
            if !trimmed.is_empty() {
                return Ok(PathBuf::from(trimmed).join("game-macro-tauri"));
            }
        }

        let home = std::env::var("HOME")
            .map(PathBuf::from)
            .map_err(|_| AppError::Config("unable to determine home directory".into()))?;
        Ok(home.join(".local").join("share").join("game-macro-tauri"))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProfileStoreSettings {
    active_profile: String,
}

impl Default for ProfileStoreSettings {
    fn default() -> Self {
        Self {
            active_profile: DEFAULT_PROFILE_NAME.into(),
        }
    }
}

/// Stores profile TOML files under the app data directory.
pub struct ProfileStore {
    root: PathBuf,
}

impl ProfileStore {
    pub fn new(root: PathBuf) -> Self {
        tracing::info!("ProfileStore root: {}", root.display());
        Self { root }
    }

    pub fn list(&self) -> AppResult<Vec<String>> {
        self.ensure_default_profile()?;
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
        names.sort();
        Ok(names)
    }

    pub fn load(&self, name: &str) -> AppResult<Profile> {
        let path = self.profile_file_path(name)?;
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
        let dir = self.profile_dir_path(name)?;
        std::fs::create_dir_all(&dir)?;

        let content = toml::to_string_pretty(profile)?;
        let path = dir.join(PROFILE_FILE_NAME);
        if profile.base.io.backup_on_save && path.exists() {
            self.backup_profile_file(&dir, &path)?;
        }
        std::fs::write(&path, &content)?;

        tracing::info!("Profile '{name}' saved");
        Ok(())
    }

    pub fn active_profile_name(&self) -> AppResult<String> {
        Ok(self.load_settings()?.active_profile)
    }

    pub fn set_active_profile_name(&self, name: &str) -> AppResult<()> {
        validate_profile_name(name)?;
        let profile_path = self.profile_file_path(name)?;
        if !profile_path.exists() {
            return Err(AppError::Config(format!("Profile not found: {name}")));
        }
        self.save_settings(&ProfileStoreSettings {
            active_profile: name.into(),
        })
    }

    pub fn load_active_or_default(&self) -> AppResult<(String, Profile)> {
        let name = self.active_profile_name()?;
        let profile = self.load_or_create_default(&name)?;
        Ok((name, profile))
    }

    fn ensure_default_profile(&self) -> AppResult<()> {
        let path = self.profile_file_path(DEFAULT_PROFILE_NAME)?;
        if !path.exists() {
            self.save(DEFAULT_PROFILE_NAME, &default_profile(DEFAULT_PROFILE_NAME))?;
        }
        Ok(())
    }

    fn load_settings(&self) -> AppResult<ProfileStoreSettings> {
        let path = self.settings_file_path();
        if !path.exists() {
            let settings = ProfileStoreSettings::default();
            self.save_settings(&settings)?;
            return Ok(settings);
        }
        let content = std::fs::read_to_string(path)?;
        let mut settings: ProfileStoreSettings = toml::from_str(&content)?;
        if settings.active_profile.trim().is_empty() {
            settings.active_profile = DEFAULT_PROFILE_NAME.into();
        }
        validate_profile_name(&settings.active_profile)?;
        Ok(settings)
    }

    fn save_settings(&self, settings: &ProfileStoreSettings) -> AppResult<()> {
        std::fs::create_dir_all(&self.root)?;
        let content = toml::to_string_pretty(settings)?;
        std::fs::write(self.settings_file_path(), content)?;
        Ok(())
    }

    fn settings_file_path(&self) -> PathBuf {
        self.root.join(SETTINGS_FILE_NAME)
    }

    fn profile_dir_path(&self, name: &str) -> AppResult<PathBuf> {
        validate_profile_name(name)?;
        Ok(self.root.join("profiles").join(name))
    }

    fn profile_file_path(&self, name: &str) -> AppResult<PathBuf> {
        Ok(self.profile_dir_path(name)?.join(PROFILE_FILE_NAME))
    }

    fn backup_profile_file(
        &self,
        profile_dir: &std::path::Path,
        profile_path: &std::path::Path,
    ) -> AppResult<()> {
        let backup_dir = profile_dir.join("backups");
        std::fs::create_dir_all(&backup_dir)?;

        let mut backup_path = backup_dir.join(format!("profile-{}.toml", timestamp_string()));
        let mut suffix = 1u32;
        while backup_path.exists() {
            backup_path = backup_dir.join(format!("profile-{}-{suffix}.toml", timestamp_string()));
            suffix += 1;
        }

        std::fs::copy(profile_path, &backup_path)?;
        tracing::info!("Profile backup written: {}", backup_path.display());
        Ok(())
    }
}

fn validate_profile_name(name: &str) -> AppResult<()> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err(AppError::Config("Profile name must not be empty".into()));
    }
    if trimmed != name {
        return Err(AppError::Config(format!(
            "Profile name must not contain leading or trailing whitespace: {name}"
        )));
    }
    if !trimmed
        .bytes()
        .all(|ch| ch.is_ascii_alphanumeric() || ch == b'_' || ch == b'-')
    {
        return Err(AppError::Config(format!(
            "Profile name may only contain letters, numbers, '_' and '-': {name}"
        )));
    }
    Ok(())
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
                confirm_hotkey: "F8".into(),
                mouse_avoid: true,
                mouse_avoid_offset_y: 80,
                mouse_avoid_settle_ms: 80,
            },
            io: IoConfig {
                backup_on_save: false,
            },
            cast_bar: CastBarConfig {
                mode: "timer".into(),
                point_id: String::new(),
                tolerance: 15,
                poll_interval_ms: 30,
                max_wait_factor: 1.5,
                roi: CastBarRoiConfig::default(),
            },
            exec: ExecConfig {
                enabled: false,
                toggle_hotkey: "F9".into(),
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
                entry_actions: vec![],
                transition_rules: vec![],
                fallback_transition: None,
            }],
            observer_lanes: vec![],
            assist_lanes: vec![],
            poll_interval_ms: 100,
            max_cycles: 0,
            state_schema: None,
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
        assert!(names.contains(&"default".to_string()));
        assert!(names.contains(&"p1".to_string()));
        assert!(names.contains(&"p2".to_string()));
    }

    #[test]
    fn test_backup_on_save_copies_previous_profile() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());
        let mut profile = default_profile("role_1");
        profile.meta.description = "old".into();
        profile.base.io.backup_on_save = true;
        store.save("role_1", &profile).unwrap();

        profile.meta.description = "new".into();
        store.save("role_1", &profile).unwrap();

        let backup_dir = tmp.path().join("profiles").join("role_1").join("backups");
        let backups = std::fs::read_dir(backup_dir)
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(backups.len(), 1);
        let content = std::fs::read_to_string(backups[0].path()).unwrap();
        assert!(content.contains("description = \"old\""));
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

    #[test]
    fn test_active_profile_defaults_to_default() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());

        let active = store.active_profile_name().unwrap();

        assert_eq!(active, "default");
        assert!(tmp.path().join("settings.toml").exists());
    }

    #[test]
    fn test_set_active_profile_requires_existing_profile() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());

        assert!(store.set_active_profile_name("missing").is_err());

        store.save("role_1", &default_profile("role_1")).unwrap();
        store.set_active_profile_name("role_1").unwrap();

        assert_eq!(store.active_profile_name().unwrap(), "role_1");
    }

    #[test]
    fn test_rejects_unsafe_profile_name() {
        let tmp = TempDir::new().unwrap();
        let store = ProfileStore::new(tmp.path().to_path_buf());

        assert!(store.save("../bad", &Profile::default()).is_err());
        assert!(store.load("bad/name").is_err());
    }
}
