//! GW2 skill import commands.

use tauri::AppHandle;

use crate::error::CommandResult;
use crate::gw2::skills::{Gw2SkillInfo, search_skills};

#[tauri::command]
pub fn gw2_skill_search(app: AppHandle, query: String) -> CommandResult<Vec<Gw2SkillInfo>> {
    Ok(search_skills(&app, &query)?)
}
