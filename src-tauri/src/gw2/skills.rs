//! Skill search over bundled Guild Wars 2 data.

use std::path::PathBuf;

use serde::Deserialize;
use tauri::{AppHandle, Manager, path::BaseDirectory};

use crate::error::{AppError, AppResult};

const SKILLS_RESOURCE_PATH: &str = "assets/gw2/skills_all.json";

#[derive(Debug, Deserialize)]
struct Gw2SkillRaw {
    id: Option<u32>,
    name: Option<String>,
    description: Option<String>,
    #[serde(default)]
    facts: Vec<serde_json::Value>,
}

#[derive(Debug, serde::Serialize)]
pub struct Gw2SkillInfo {
    pub id: u32,
    pub name: String,
    pub description: String,
    pub cooldown_ms: u32,
    pub radius: u32,
}

pub fn search_skills(app: &AppHandle, query: &str) -> AppResult<Vec<Gw2SkillInfo>> {
    let path = find_skills_json(Some(app))?;
    search_skills_file(path, query)
}

fn search_skills_file(path: PathBuf, query: &str) -> AppResult<Vec<Gw2SkillInfo>> {
    let content = std::fs::read_to_string(&path)?;
    let raw_skills: Vec<Gw2SkillRaw> = serde_json::from_str(&content)?;

    let query = query.trim().to_lowercase();
    let mut results: Vec<Gw2SkillInfo> = raw_skills
        .into_iter()
        .filter_map(|s| {
            let name = s.name.unwrap_or_default();
            if !query.is_empty() && !name.to_lowercase().contains(&query) {
                return None;
            }
            let cooldown_ms = extract_cooldown(&s.facts);
            let radius = extract_radius(&s.facts);
            Some(Gw2SkillInfo {
                id: s.id.unwrap_or(0),
                name,
                description: s.description.unwrap_or_default(),
                cooldown_ms,
                radius,
            })
        })
        .take(50)
        .collect();

    results.sort_by_key(|s| s.name.clone());
    Ok(results)
}

fn find_skills_json(app: Option<&AppHandle>) -> AppResult<PathBuf> {
    if let Some(app) = app {
        match app
            .path()
            .resolve(SKILLS_RESOURCE_PATH, BaseDirectory::Resource)
        {
            Ok(path) if path.exists() => {
                tracing::info!("using bundled GW2 skills file: {}", path.display());
                return Ok(path);
            }
            Ok(path) => {
                tracing::debug!("bundled GW2 skills file missing: {}", path.display());
            }
            Err(error) => {
                tracing::debug!(error = %error, "failed to resolve bundled GW2 skills file");
            }
        }
    }

    let manifest_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(SKILLS_RESOURCE_PATH);
    if manifest_path.exists() {
        tracing::info!(
            "using development GW2 skills file: {}",
            manifest_path.display()
        );
        return Ok(manifest_path);
    }

    let cwd_path = PathBuf::from(SKILLS_RESOURCE_PATH);
    if cwd_path.exists() {
        tracing::info!("using cwd GW2 skills file: {}", cwd_path.display());
        return Ok(cwd_path);
    }

    Err(AppError::Config(format!(
        "skills_all.json not found in bundled resources or {SKILLS_RESOURCE_PATH}"
    )))
}

fn extract_cooldown(facts: &[serde_json::Value]) -> u32 {
    for f in facts {
        if f.get("type").and_then(|v| v.as_str()) == Some("Recharge") {
            if let Some(v) = f.get("value").and_then(|v| v.as_f64()) {
                return (v * 1000.0) as u32;
            }
        }
    }
    0
}

fn extract_radius(facts: &[serde_json::Value]) -> u32 {
    for f in facts {
        if f.get("type").and_then(|v| v.as_str()) == Some("Distance") {
            if let Some(v) = f.get("distance").and_then(|v| v.as_f64()) {
                return v as u32;
            }
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn extract_cooldown_from_recharge_fact() {
        let facts = vec![json!({ "type": "Recharge", "value": 12.5 })];
        assert_eq!(extract_cooldown(&facts), 12_500);
    }

    #[test]
    fn extract_radius_from_distance_fact() {
        let facts = vec![json!({ "type": "Distance", "distance": 900 })];
        assert_eq!(extract_radius(&facts), 900);
    }

    #[test]
    fn development_asset_path_is_repo_relative() {
        let path = find_skills_json(None).expect("development skills data must exist");
        assert!(path.ends_with(SKILLS_RESOURCE_PATH));
    }
}
