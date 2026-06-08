//! Profile TOML 持久化

use crate::error::{AppError, AppResult};
use crate::models::profile::Profile;
use std::path::PathBuf;

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
}
