//! Capture commands.

use std::path::PathBuf;
use std::time::Duration;

use enigo::{Coordinate, Mouse};
use serde::Serialize;

use crate::capture::capturer::CaptureManager;
use crate::capture::cast_bar_roi::{
    CastBarRoiRequest, CastBarRoiSample, sample_cast_bar_roi, validate_cast_bar_roi_request,
};
use crate::error::{AppError, CommandResult};
use crate::models::base::PickConfig;
use crate::store::profile_store::ProfileStore;

#[derive(Debug, Clone, Serialize)]
pub struct CaptureResult {
    pub monitor: String,
    pub x: i32,
    pub y: i32,
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub hex: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CaptureDiagnostics {
    pub monitor_count: usize,
    pub monitors: Vec<String>,
    pub cursor_x: i32,
    pub cursor_y: i32,
    pub cursor_monitor: String,
    pub sample: Option<CaptureResult>,
    pub sample_error: Option<String>,
}

fn app_data_dir() -> Result<PathBuf, AppError> {
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

fn load_pick_config() -> Result<PickConfig, AppError> {
    let store = ProfileStore::new(app_data_dir()?);
    Ok(store.load_or_create_default("default")?.base.pick)
}

fn avoid_target_y(y: i32, offset_y: i32) -> i32 {
    y.saturating_add(offset_y)
}

fn avoid_cursor_if_configured(enigo: &mut enigo::Enigo, x: i32, y: i32, pick: &PickConfig) -> bool {
    if !pick.mouse_avoid {
        return false;
    }

    let target_y = avoid_target_y(y, pick.mouse_avoid_offset_y);
    match enigo.move_mouse(x, target_y, Coordinate::Abs) {
        Ok(()) => {
            if pick.mouse_avoid_settle_ms > 0 {
                std::thread::sleep(Duration::from_millis(pick.mouse_avoid_settle_ms as u64));
            }
            true
        }
        Err(error) => {
            tracing::warn!("cursor avoid move failed: {error}");
            false
        }
    }
}

fn restore_cursor(enigo: &mut enigo::Enigo, x: i32, y: i32) {
    if let Err(error) = enigo.move_mouse(x, y, Coordinate::Abs) {
        tracing::warn!("cursor restore failed: {error}");
    }
}

fn capture_result_from_sample(
    monitor: String,
    x: i32,
    y: i32,
    sample: (u8, u8, u8),
) -> CaptureResult {
    let (r, g, b) = sample;
    let hex = format!("#{r:02X}{g:02X}{b:02X}");
    CaptureResult {
        monitor,
        x,
        y,
        r,
        g,
        b,
        hex,
    }
}

#[tauri::command]
pub fn capture_sample(x: i32, y: i32) -> CommandResult<(u8, u8, u8)> {
    let mut capture = CaptureManager::new().map_err(AppError::Capture)?;
    Ok(capture
        .sample_pixel_abs(x, y)
        .ok_or_else(|| AppError::Capture("sample failed".into()))?)
}

#[tauri::command]
pub fn capture_at_cursor() -> CommandResult<CaptureResult> {
    let mut enigo = enigo::Enigo::new(&enigo::Settings::default())
        .map_err(|e| AppError::Input(format!("enigo init failed: {e}")))?;
    let (x, y) = enigo
        .location()
        .map_err(|e| AppError::Input(format!("cursor location failed: {e}")))?;
    let pick = load_pick_config().unwrap_or_else(|error| {
        tracing::warn!("load pick config failed, capture uses cursor in-place: {error}");
        PickConfig::default()
    });

    let mut capture = CaptureManager::new().map_err(AppError::Capture)?;
    let monitor = capture.monitor_for_point(x, y);
    let moved_cursor = avoid_cursor_if_configured(&mut enigo, x, y, &pick);
    let sample = capture.sample_pixel_abs(x, y);
    if moved_cursor {
        restore_cursor(&mut enigo, x, y);
    }
    let sample = sample.ok_or_else(|| AppError::Capture("sample failed".into()))?;

    let result = capture_result_from_sample(monitor, x, y, sample);
    tracing::info!(
        "F8 capture: {} ({},{}) -> {}",
        result.monitor,
        result.x,
        result.y,
        result.hex
    );

    Ok(result)
}

#[tauri::command]
pub fn capture_diagnostics() -> CommandResult<CaptureDiagnostics> {
    let enigo = enigo::Enigo::new(&enigo::Settings::default())
        .map_err(|e| AppError::Input(format!("enigo init failed: {e}")))?;
    let (x, y) = enigo
        .location()
        .map_err(|e| AppError::Input(format!("cursor location failed: {e}")))?;

    let mut capture = CaptureManager::new().map_err(AppError::Capture)?;
    let monitors = capture.monitor_names();
    let cursor_monitor = capture.monitor_for_point(x, y);
    let sample = capture.sample_pixel_abs(x, y);
    let sample_result =
        sample.map(|rgb| capture_result_from_sample(cursor_monitor.clone(), x, y, rgb));
    let sample_error = if sample_result.is_some() {
        None
    } else {
        Some("sample failed at current cursor".into())
    };

    Ok(CaptureDiagnostics {
        monitor_count: monitors.len(),
        monitors,
        cursor_x: x,
        cursor_y: y,
        cursor_monitor,
        sample: sample_result,
        sample_error,
    })
}

#[tauri::command]
pub fn capture_cast_bar_roi(request: CastBarRoiRequest) -> CommandResult<CastBarRoiSample> {
    validate_cast_bar_roi_request(&request).map_err(AppError::Capture)?;
    let capture = CaptureManager::new().map_err(AppError::Capture)?;
    sample_cast_bar_roi(&capture, &request).map_err(|error| AppError::Capture(error).into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_avoid_target_y_saturates() {
        assert_eq!(avoid_target_y(i32::MAX, 80), i32::MAX);
        assert_eq!(avoid_target_y(i32::MIN, -80), i32::MIN);
        assert_eq!(avoid_target_y(100, -80), 20);
    }

    #[test]
    fn test_capture_result_from_sample_formats_hex() {
        let result = capture_result_from_sample("primary".into(), 10, 20, (1, 171, 255));

        assert_eq!(result.monitor, "primary");
        assert_eq!(result.x, 10);
        assert_eq!(result.y, 20);
        assert_eq!(result.hex, "#01ABFF");
    }
}
