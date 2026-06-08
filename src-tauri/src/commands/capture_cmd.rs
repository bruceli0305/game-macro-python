//! 取色会话命令

use crate::ast::evaluator::PixelSampler;
use crate::capture::capturer::DirectPixelSampler;
use crate::error::{AppError, CommandResult};
use enigo::Mouse;
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct CaptureResult {
    pub x: i32,
    pub y: i32,
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub hex: String,
}

/// 采样指定坐标的像素
#[tauri::command]
pub fn capture_sample(x: i32, y: i32) -> CommandResult<(u8, u8, u8)> {
    let sampler = DirectPixelSampler;
    Ok(sampler
        .sample_rgb_abs("primary", x, y, "single", 0)
        .ok_or_else(|| AppError::Capture("sample failed".into()))?)
}

/// 获取当前鼠标位置并采样像素
#[tauri::command]
pub fn capture_at_cursor() -> CommandResult<CaptureResult> {
    // 使用 enigo 获取鼠标位置
    let enigo = enigo::Enigo::new(&enigo::Settings::default())
        .map_err(|e| AppError::Input(format!("enigo init failed: {e}")))?;
    let (x, y) = enigo
        .location()
        .map_err(|e| AppError::Input(format!("cursor location failed: {e}")))?;

    let sampler = DirectPixelSampler;
    let (r, g, b) = sampler
        .sample_rgb_abs("primary", x, y, "single", 0)
        .ok_or_else(|| AppError::Capture("sample failed".into()))?;

    let hex = format!("#{r:02X}{g:02X}{b:02X}");
    tracing::info!("F8 取色: ({x},{y}) → {hex}");

    Ok(CaptureResult { x, y, r, g, b, hex })
}
