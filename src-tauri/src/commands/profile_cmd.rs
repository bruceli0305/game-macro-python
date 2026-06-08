//! Profile 配置 CRUD 命令

use crate::error::{AppError, AppResult, CommandResult};
use crate::models::profile::Profile;
use crate::store::profile_store::ProfileStore;
use serde::Serialize;
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
    let profile = store.load(&name)?;
    Ok(serde_json::to_string_pretty(&profile).map_err(AppError::from)?)
}

#[tauri::command]
pub fn profile_save(name: String, content: String) -> CommandResult<()> {
    let store = get_store()?;
    let profile: Profile = serde_json::from_str(&content).map_err(AppError::from)?;
    Ok(store.save(&name, &profile)?)
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
