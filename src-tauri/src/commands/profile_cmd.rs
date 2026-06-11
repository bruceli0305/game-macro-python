//! Profile configuration CRUD commands.
use crate::error::{AppError, AppResult, CommandResult};
use crate::models::profile::Profile;
use crate::profile::validation::validate_profile_references;
use crate::store::profile_store::{ProfileStore, app_data_dir};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct ProfileInfo {
    pub name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ActiveProfileInfo {
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
pub fn profile_get_active() -> CommandResult<ActiveProfileInfo> {
    let store = get_store()?;
    Ok(ActiveProfileInfo {
        name: store.active_profile_name()?,
    })
}

#[tauri::command]
pub fn profile_set_active(name: String) -> CommandResult<()> {
    let store = get_store()?;
    Ok(store.set_active_profile_name(&name)?)
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
