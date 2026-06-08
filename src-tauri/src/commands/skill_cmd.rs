//! GW2 技能导入命令

use crate::error::{AppError, AppResult, CommandResult};
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Debug, Deserialize)]
struct Gw2SkillRaw {
    id: Option<u32>,
    name: Option<String>,
    description: Option<String>,
    #[serde(rename = "type")]
    skill_type: Option<String>,
    weapon_type: Option<String>,
    slot: Option<String>,
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

/// 从旧项目的 GW2 JSON 文件中解析技能列表
#[tauri::command]
pub fn gw2_skill_search(_query: String) -> CommandResult<Vec<Gw2SkillInfo>> {
    Ok(gw2_skill_search_inner(&_query)?)
}

fn gw2_skill_search_inner(_query: &str) -> AppResult<Vec<Gw2SkillInfo>> {
    // 查找 skills_all.json
    let path = find_skills_json()?;
    let content = std::fs::read_to_string(&path)?;

    let raw_skills: Vec<Gw2SkillRaw> = serde_json::from_str(&content)?;

    let query = _query.trim().to_lowercase();
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

fn find_skills_json() -> AppResult<PathBuf> {
    // Tauri dev 模式 cwd 在 src-tauri/，所以 assets/gw2/ 直接可用
    let candidates: Vec<PathBuf> = vec![
        PathBuf::from("assets/gw2/skills_all.json"),
        PathBuf::from("../assets/gw2/skills_all.json"),
        PathBuf::from("../python-legacy/assets/json/gw2/skills_all.json"),
    ];
    for p in &candidates {
        if p.exists() {
            tracing::info!("找到技能文件: {}", p.display());
            return Ok(p.clone());
        }
        tracing::debug!("尝试路径(未找到): {}", p.display());
    }
    Err(AppError::Config(
        "skills_all.json not found; place it under src-tauri/assets/gw2/".into(),
    ))
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
    fn test_extract_cooldown_from_recharge_fact() {
        let facts = vec![json!({ "type": "Recharge", "value": 12.5 })];
        assert_eq!(extract_cooldown(&facts), 12_500);
    }

    #[test]
    fn test_extract_radius_from_distance_fact() {
        let facts = vec![json!({ "type": "Distance", "distance": 900 })];
        assert_eq!(extract_radius(&facts), 900);
    }
}
