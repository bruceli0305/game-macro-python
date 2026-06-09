use std::sync::Mutex;
use std::time::Instant;

use serde::{Deserialize, Serialize};

use crate::ast::evaluator::{CastBarRoiProvider, CastBarRoiState, CastBarRoiStats};
use crate::capture::capturer::CaptureManager;
use crate::models::base::CastBarRoiConfig;
use crate::models::skill::ColorRGB;

#[derive(Debug, Clone, Deserialize)]
pub struct CastBarRoiRequest {
    pub monitor: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub baseline_color: ColorRGB,
    pub diff_threshold: u8,
    pub min_changed_ratio: f64,
    #[serde(default)]
    pub border_enabled: bool,
    pub border_color: ColorRGB,
    pub border_tolerance: u8,
    pub min_border_match_ratio: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct CastBarRoiSample {
    pub monitor: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub pixel_count: u32,
    pub average_color: ColorRGB,
    pub changed_pixel_count: u32,
    pub changed_ratio: f64,
    pub changed_from_baseline: bool,
    pub border_pixel_count: u32,
    pub border_match_count: u32,
    pub border_match_ratio: f64,
    pub border_visible: bool,
}

#[derive(Debug, Default)]
struct CastBarRoiTracker {
    changed_frames: u32,
    border_frames: u32,
    gone_frames: u32,
    cache_tick_ms: Option<u64>,
    cached_state: Option<CastBarRoiState>,
    cached_unavailable: bool,
    stats: CastBarRoiStats,
}

pub struct ScreenCastBarRoiProvider {
    config: CastBarRoiConfig,
    tracker: Mutex<CastBarRoiTracker>,
}

impl ScreenCastBarRoiProvider {
    pub fn new(config: CastBarRoiConfig) -> Self {
        Self {
            config,
            tracker: Mutex::new(CastBarRoiTracker::default()),
        }
    }

    fn cached_state_for_tick(&self) -> Option<Option<CastBarRoiState>> {
        let mut tracker = self.tracker.lock().ok()?;
        if tracker.cached_unavailable || tracker.cached_state.is_some() {
            tracker.stats.cache_hit_count += 1;
            return Some(tracker.cached_state);
        }
        None
    }

    fn sample_state(&self) -> (Option<CastBarRoiState>, u64, String) {
        let started = Instant::now();
        let result = self.sample_state_inner();
        let latency_us = started.elapsed().as_micros().min(u128::from(u64::MAX)) as u64;
        match result {
            Ok(state) => (Some(state), latency_us, String::new()),
            Err(error) => (None, latency_us, error),
        }
    }

    fn sample_state_inner(&self) -> Result<CastBarRoiState, String> {
        if !self.config.enabled {
            return Err("cast bar ROI disabled".into());
        }
        if self.config.width == 0 || self.config.height == 0 {
            return Err("cast bar ROI has empty dimensions".into());
        }

        let capture = CaptureManager::new()?;
        let request = CastBarRoiRequest::from(&self.config);
        let sample = sample_cast_bar_roi(&capture, &request)?;
        let visible_raw = sample.changed_from_baseline || sample.border_visible;
        let gone_raw = !visible_raw;

        let mut tracker = self
            .tracker
            .lock()
            .map_err(|_| "cast bar ROI tracker lock poisoned".to_string())?;
        tracker.changed_frames =
            next_frame_count(tracker.changed_frames, sample.changed_from_baseline);
        tracker.border_frames = next_frame_count(tracker.border_frames, sample.border_visible);
        tracker.gone_frames = next_frame_count(tracker.gone_frames, gone_raw);

        let confirm_frames = self.config.confirm_frames.max(1);
        Ok(CastBarRoiState {
            changed_from_baseline: tracker.changed_frames >= confirm_frames,
            border_visible: tracker.border_frames >= confirm_frames,
            gone: tracker.gone_frames >= confirm_frames,
            changed_ratio: sample.changed_ratio,
            border_match_ratio: sample.border_match_ratio,
        })
    }

    fn store_tick_result(&self, state: Option<CastBarRoiState>, latency_us: u64, error: String) {
        let Ok(mut tracker) = self.tracker.lock() else {
            return;
        };
        tracker.cached_state = state;
        tracker.cached_unavailable = state.is_none();
        tracker.stats.enabled = self.config.enabled;
        tracker.stats.sample_count += 1;
        tracker.stats.last_latency_us = latency_us;
        tracker.stats.max_latency_us = tracker.stats.max_latency_us.max(latency_us);
        let total_latency = tracker
            .stats
            .avg_latency_us
            .saturating_mul(tracker.stats.sample_count.saturating_sub(1))
            .saturating_add(latency_us);
        tracker.stats.avg_latency_us = total_latency / tracker.stats.sample_count.max(1);
        tracker.stats.last_error = error;

        if let Some(state) = state {
            tracker.stats.last_changed_ratio = state.changed_ratio;
            tracker.stats.last_border_match_ratio = state.border_match_ratio;
            tracker.stats.last_changed_from_baseline = state.changed_from_baseline;
            tracker.stats.last_border_visible = state.border_visible;
            tracker.stats.last_gone = state.gone;
        } else {
            tracker.stats.failed_sample_count += 1;
        }
    }
}

impl CastBarRoiProvider for ScreenCastBarRoiProvider {
    fn begin_tick(&self, tick_ms: u64) {
        let Ok(mut tracker) = self.tracker.lock() else {
            return;
        };
        if tracker.cache_tick_ms == Some(tick_ms) {
            return;
        }
        tracker.cache_tick_ms = Some(tick_ms);
        tracker.cached_state = None;
        tracker.cached_unavailable = false;
    }

    fn get_cast_bar_roi_state(&self) -> Option<CastBarRoiState> {
        if let Some(cached_state) = self.cached_state_for_tick() {
            return cached_state;
        }

        let (state, latency_us, error) = self.sample_state();
        self.store_tick_result(state, latency_us, error);
        state
    }

    fn get_cast_bar_roi_stats(&self) -> Option<CastBarRoiStats> {
        let tracker = self.tracker.lock().ok()?;
        Some(tracker.stats.clone())
    }
}

impl From<&CastBarRoiConfig> for CastBarRoiRequest {
    fn from(config: &CastBarRoiConfig) -> Self {
        Self {
            monitor: config.monitor.clone(),
            x: config.x,
            y: config.y,
            width: config.width,
            height: config.height,
            baseline_color: config.baseline_color.clone(),
            diff_threshold: config.diff_threshold,
            min_changed_ratio: config.min_changed_ratio,
            border_enabled: config.border_enabled,
            border_color: config.border_color.clone(),
            border_tolerance: config.border_tolerance,
            min_border_match_ratio: config.min_border_match_ratio,
        }
    }
}

pub fn validate_cast_bar_roi_request(request: &CastBarRoiRequest) -> Result<(), String> {
    if request.width == 0 || request.height == 0 || request.width > 2000 || request.height > 500 {
        return Err("cast bar ROI width must be 1-2000 and height must be 1-500".into());
    }
    if !request.min_changed_ratio.is_finite()
        || request.min_changed_ratio < 0.0
        || request.min_changed_ratio > 1.0
    {
        return Err("cast bar ROI changed ratio must be between 0 and 1".into());
    }
    if !request.min_border_match_ratio.is_finite()
        || request.min_border_match_ratio < 0.0
        || request.min_border_match_ratio > 1.0
    {
        return Err("cast bar ROI border match ratio must be between 0 and 1".into());
    }
    Ok(())
}

pub fn sample_cast_bar_roi(
    capture: &CaptureManager,
    request: &CastBarRoiRequest,
) -> Result<CastBarRoiSample, String> {
    validate_cast_bar_roi_request(request)?;

    let monitor = if request.monitor.trim().is_empty() {
        capture.monitor_for_point(request.x, request.y)
    } else {
        request.monitor.trim().to_string()
    };
    let image = capture.capture_now(&monitor)?;
    let (x_rel, y_rel) = capture.abs_to_rel(request.x, request.y, &monitor);
    let x0 = x_rel.max(0) as u32;
    let y0 = y_rel.max(0) as u32;
    let x1 = (x_rel.saturating_add(request.width as i32)).max(0) as u32;
    let y1 = (y_rel.saturating_add(request.height as i32)).max(0) as u32;
    let x1 = x1.min(image.width());
    let y1 = y1.min(image.height());

    sample_cast_bar_roi_image(&image, &monitor, request, x0, y0, x1, y1)
}

fn sample_cast_bar_roi_image(
    image: &image::RgbaImage,
    monitor: &str,
    request: &CastBarRoiRequest,
    x0: u32,
    y0: u32,
    x1: u32,
    y1: u32,
) -> Result<CastBarRoiSample, String> {
    if x0 >= x1 || y0 >= y1 {
        return Err("cast bar ROI is outside the selected monitor".into());
    }

    let mut sum_r: u64 = 0;
    let mut sum_g: u64 = 0;
    let mut sum_b: u64 = 0;
    let mut changed_pixel_count = 0u32;
    let mut border_pixel_count = 0u32;
    let mut border_match_count = 0u32;
    let mut pixel_count = 0u32;

    for py in y0..y1 {
        for px in x0..x1 {
            let pixel = image.get_pixel(px, py);
            let rgb = ColorRGB {
                r: pixel.0[0],
                g: pixel.0[1],
                b: pixel.0[2],
            };
            sum_r += rgb.r as u64;
            sum_g += rgb.g as u64;
            sum_b += rgb.b as u64;
            pixel_count += 1;

            if color_delta(&rgb, &request.baseline_color) > request.diff_threshold {
                changed_pixel_count += 1;
            }

            let is_border = px == x0 || px + 1 == x1 || py == y0 || py + 1 == y1;
            if is_border {
                border_pixel_count += 1;
                if color_delta(&rgb, &request.border_color) <= request.border_tolerance {
                    border_match_count += 1;
                }
            }
        }
    }

    let changed_ratio = ratio(changed_pixel_count, pixel_count);
    let border_match_ratio = ratio(border_match_count, border_pixel_count);
    let average_color = ColorRGB {
        r: (sum_r / pixel_count as u64) as u8,
        g: (sum_g / pixel_count as u64) as u8,
        b: (sum_b / pixel_count as u64) as u8,
    };

    Ok(CastBarRoiSample {
        monitor: monitor.to_string(),
        x: request.x,
        y: request.y,
        width: x1 - x0,
        height: y1 - y0,
        pixel_count,
        average_color,
        changed_pixel_count,
        changed_ratio,
        changed_from_baseline: changed_ratio >= request.min_changed_ratio,
        border_pixel_count,
        border_match_count,
        border_match_ratio,
        border_visible: request.border_enabled
            && border_match_ratio >= request.min_border_match_ratio,
    })
}

fn color_delta(left: &ColorRGB, right: &ColorRGB) -> u8 {
    let dr = left.r.abs_diff(right.r);
    let dg = left.g.abs_diff(right.g);
    let db = left.b.abs_diff(right.b);
    dr.max(dg).max(db)
}

fn ratio(count: u32, total: u32) -> f64 {
    if total == 0 {
        0.0
    } else {
        count as f64 / total as f64
    }
}

fn next_frame_count(current: u32, matched: bool) -> u32 {
    if matched {
        current.saturating_add(1)
    } else {
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> CastBarRoiRequest {
        CastBarRoiRequest {
            monitor: "primary".into(),
            x: 0,
            y: 0,
            width: 2,
            height: 2,
            baseline_color: ColorRGB {
                r: 10,
                g: 10,
                b: 10,
            },
            diff_threshold: 5,
            min_changed_ratio: 0.5,
            border_enabled: true,
            border_color: ColorRGB {
                r: 40,
                g: 40,
                b: 40,
            },
            border_tolerance: 0,
            min_border_match_ratio: 0.5,
        }
    }

    #[test]
    fn test_color_delta_uses_max_channel_difference() {
        assert_eq!(
            color_delta(
                &ColorRGB {
                    r: 10,
                    g: 20,
                    b: 30
                },
                &ColorRGB { r: 9, g: 35, b: 25 }
            ),
            15
        );
    }

    #[test]
    fn test_ratio_handles_empty_total() {
        assert_eq!(ratio(3, 0), 0.0);
        assert_eq!(ratio(1, 4), 0.25);
    }

    #[test]
    fn test_sample_cast_bar_roi_image_detects_changed_and_border() {
        let mut image = image::RgbaImage::new(2, 2);
        for pixel in image.pixels_mut() {
            *pixel = image::Rgba([40, 40, 40, 255]);
        }

        let sample = sample_cast_bar_roi_image(&image, "primary", &request(), 0, 0, 2, 2).unwrap();

        assert_eq!(sample.pixel_count, 4);
        assert!(sample.changed_from_baseline);
        assert_eq!(sample.changed_ratio, 1.0);
        assert!(sample.border_visible);
        assert_eq!(sample.border_match_ratio, 1.0);
    }

    #[test]
    fn test_border_detection_can_be_disabled() {
        let mut image = image::RgbaImage::new(2, 2);
        for pixel in image.pixels_mut() {
            *pixel = image::Rgba([40, 40, 40, 255]);
        }
        let mut request = request();
        request.border_enabled = false;

        let sample = sample_cast_bar_roi_image(&image, "primary", &request, 0, 0, 2, 2).unwrap();

        assert!(!sample.border_visible);
        assert_eq!(sample.border_match_ratio, 1.0);
    }

    #[test]
    fn test_provider_caches_unavailable_result_within_tick() {
        let provider = ScreenCastBarRoiProvider::new(CastBarRoiConfig {
            enabled: false,
            ..Default::default()
        });

        provider.begin_tick(100);
        assert!(provider.get_cast_bar_roi_state().is_none());
        assert!(provider.get_cast_bar_roi_state().is_none());
        let stats = provider.get_cast_bar_roi_stats().unwrap();
        assert_eq!(stats.sample_count, 1);
        assert_eq!(stats.cache_hit_count, 1);
        assert_eq!(stats.failed_sample_count, 1);

        provider.begin_tick(110);
        assert!(provider.get_cast_bar_roi_state().is_none());
        let stats = provider.get_cast_bar_roi_stats().unwrap();
        assert_eq!(stats.sample_count, 2);
        assert_eq!(stats.cache_hit_count, 1);
        assert_eq!(stats.failed_sample_count, 2);
    }
}
