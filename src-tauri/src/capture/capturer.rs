//! xcap 截屏封装 + PixelSampler trait 实现 + 快照缓存 + 退避
//!
//! 运行时截屏和像素采样实现

use crate::ast::evaluator::PixelSampler;
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use xcap::Monitor;

// ---- xcap Monitor 辅助函数 ----

/// 安全获取 monitor.x()，失败回退 0
fn monitor_x(m: &Monitor) -> i32 {
    m.x().unwrap_or(0)
}
fn monitor_y(m: &Monitor) -> i32 {
    m.y().unwrap_or(0)
}
fn monitor_w(m: &Monitor) -> u32 {
    m.width().unwrap_or(1920)
}
fn monitor_h(m: &Monitor) -> u32 {
    m.height().unwrap_or(1080)
}
fn monitor_is_primary(m: &Monitor) -> bool {
    m.is_primary().unwrap_or(false)
}
fn monitor_name(m: &Monitor) -> String {
    m.friendly_name()
        .unwrap_or_else(|_| format!("monitor_{}", m.id().unwrap_or(0)))
}

// ---------------------------------------------------------------------------
// Snapshot
// ---------------------------------------------------------------------------

#[derive(Debug)]
pub enum SnapshotResult {
    Ok {
        monitor_name: String,
        captured_at: Instant,
    },
    Unavailable {
        error: String,
        retry_after_ms: u64,
    },
}

// ---------------------------------------------------------------------------
// CaptureManager
// ---------------------------------------------------------------------------

pub struct CaptureManager {
    monitors: Vec<Monitor>,
    cached_snapshot: Option<(String, Instant)>,
    cache_ttl: Duration,
    base_backoff_ms: u64,
    max_backoff_ms: u64,
    fail_count: u32,
    next_allowed_at: Instant,
    last_error: String,
}

impl CaptureManager {
    pub fn new() -> Result<Self, String> {
        let monitors = Monitor::all().map_err(|e| format!("xcap Monitor::all() failed: {e}"))?;
        Ok(Self {
            monitors,
            cached_snapshot: None,
            cache_ttl: Duration::from_millis(30),
            base_backoff_ms: 50,
            max_backoff_ms: 1000,
            fail_count: 0,
            next_allowed_at: Instant::now(),
            last_error: String::new(),
        })
    }

    pub fn monitor_names(&self) -> Vec<String> {
        self.monitors.iter().map(monitor_name).collect()
    }

    pub fn find_monitor(&self, name: &str) -> Option<&Monitor> {
        let key = name.trim().to_lowercase();
        if key == "primary" || key.is_empty() {
            self.monitors.iter().find(|m| monitor_is_primary(m))
        } else if key == "all" {
            self.monitors.first()
        } else {
            self.monitors
                .iter()
                .find(|m| monitor_name(m).to_lowercase() == key)
        }
    }

    pub fn abs_to_rel(&self, x_abs: i32, y_abs: i32, monitor_name: &str) -> (i32, i32) {
        match self.find_monitor(monitor_name) {
            Some(m) => (x_abs - monitor_x(m), y_abs - monitor_y(m)),
            None => (x_abs, y_abs),
        }
    }

    pub fn monitor_for_point(&self, x_abs: i32, y_abs: i32) -> String {
        for m in &self.monitors {
            let mx = monitor_x(m);
            let my = monitor_y(m);
            let mw = monitor_w(m) as i32;
            let mh = monitor_h(m) as i32;
            if x_abs >= mx && x_abs < mx + mw && y_abs >= my && y_abs < my + mh {
                return monitor_name(m);
            }
        }
        self.monitors
            .iter()
            .find(|m| monitor_is_primary(m))
            .map(monitor_name)
            .unwrap_or_else(|| "primary".into())
    }

    pub fn get_snapshot(&mut self, monitor_name: &str) -> SnapshotResult {
        let now = Instant::now();

        if now < self.next_allowed_at {
            let retry_after = self.next_allowed_at.duration_since(now).as_millis() as u64;
            return SnapshotResult::Unavailable {
                error: self.last_error.clone(),
                retry_after_ms: retry_after,
            };
        }

        if let Some((ref cached_name, cached_at)) = self.cached_snapshot {
            if cached_name == monitor_name {
                let age = now.duration_since(cached_at);
                if age <= self.cache_ttl {
                    return SnapshotResult::Ok {
                        monitor_name: monitor_name.into(),
                        captured_at: cached_at,
                    };
                }
            }
        }

        let monitor = match self.find_monitor(monitor_name) {
            Some(m) => m,
            None => {
                return SnapshotResult::Unavailable {
                    error: format!("monitor not found: {monitor_name}"),
                    retry_after_ms: 100,
                };
            }
        };

        match monitor.capture_image() {
            Ok(_image) => {
                self.fail_count = 0;
                self.next_allowed_at = now;
                self.last_error.clear();
                let captured_at = Instant::now();
                self.cached_snapshot = Some((monitor_name.into(), captured_at));
                SnapshotResult::Ok {
                    monitor_name: monitor_name.into(),
                    captured_at,
                }
            }
            Err(e) => {
                self.fail_count += 1;
                let backoff = self.base_backoff_ms * (1u64 << self.fail_count.min(6));
                let backoff = backoff.min(self.max_backoff_ms);
                self.next_allowed_at = now + Duration::from_millis(backoff);
                self.last_error = format!("capture failed: {e}");
                SnapshotResult::Unavailable {
                    error: self.last_error.clone(),
                    retry_after_ms: backoff,
                }
            }
        }
    }

    pub fn capture_now(&self, monitor_name: &str) -> Result<image::RgbaImage, String> {
        let monitor = self
            .find_monitor(monitor_name)
            .ok_or_else(|| format!("monitor not found: {monitor_name}"))?;
        monitor
            .capture_image()
            .map_err(|e| format!("capture failed: {e}"))
    }

    pub fn sample_pixel(
        &mut self,
        monitor_name: &str,
        x_rel: u32,
        y_rel: u32,
    ) -> Option<(u8, u8, u8)> {
        let monitor = self.find_monitor(monitor_name)?;
        let image = monitor.capture_image().ok()?;
        let pixel = image.get_pixel(x_rel, y_rel);
        Some((pixel.0[0], pixel.0[1], pixel.0[2]))
    }

    pub fn sample_pixel_abs(&mut self, x_abs: i32, y_abs: i32) -> Option<(u8, u8, u8)> {
        let monitor_name = self.monitor_for_point(x_abs, y_abs);
        let (x_rel, y_rel) = self.abs_to_rel(x_abs, y_abs, &monitor_name);
        if x_rel < 0 || y_rel < 0 {
            return None;
        }
        self.sample_pixel(&monitor_name, x_rel as u32, y_rel as u32)
    }

    pub fn sample_rect_mean(
        &mut self,
        monitor_name: &str,
        x_rel: i32,
        y_rel: i32,
        radius: u8,
    ) -> Option<(u8, u8, u8)> {
        let monitor = self.find_monitor(monitor_name)?;
        let image = monitor.capture_image().ok()?;
        let r = radius as i32;
        let mut sum_r: u64 = 0;
        let mut sum_g: u64 = 0;
        let mut sum_b: u64 = 0;
        let mut count: u64 = 0;
        for dy in -r..=r {
            for dx in -r..=r {
                let px = (x_rel + dx).max(0) as u32;
                let py = (y_rel + dy).max(0) as u32;
                if px < image.width() && py < image.height() {
                    let p = image.get_pixel(px, py);
                    sum_r += p.0[0] as u64;
                    sum_g += p.0[1] as u64;
                    sum_b += p.0[2] as u64;
                    count += 1;
                }
            }
        }
        if count == 0 {
            return None;
        }
        Some((
            (sum_r / count) as u8,
            (sum_g / count) as u8,
            (sum_b / count) as u8,
        ))
    }
}

// ---------------------------------------------------------------------------
// DirectPixelSampler — 无缓存直接采样（供 AST evaluator 使用）
// ---------------------------------------------------------------------------

pub struct DirectPixelSampler;

impl PixelSampler for DirectPixelSampler {
    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        sample_mode: &str,
        sample_radius: u8,
    ) -> Option<(u8, u8, u8)> {
        let monitors = Monitor::all().ok()?;
        let m = if monitor.is_empty() || monitor == "primary" {
            monitors.iter().find(|m| monitor_is_primary(m))?
        } else {
            monitors.iter().find(|m| monitor_name(m) == monitor)?
        };
        let mx = monitor_x(m);
        let my = monitor_y(m);
        let mw = monitor_w(m);
        let mh = monitor_h(m);

        let x_rel = x_abs - mx;
        let y_rel = y_abs - my;
        if x_rel < 0 || y_rel < 0 || x_rel >= mw as i32 || y_rel >= mh as i32 {
            return None;
        }

        let image = m.capture_image().ok()?;

        if sample_mode == "mean_square" && sample_radius > 0 {
            let r = sample_radius as i32;
            let mut sum_r: u64 = 0;
            let mut sum_g: u64 = 0;
            let mut sum_b: u64 = 0;
            let mut count: u64 = 0;
            for dy in -r..=r {
                for dx in -r..=r {
                    let px = (x_rel + dx).max(0).min(mw as i32 - 1) as u32;
                    let py = (y_rel + dy).max(0).min(mh as i32 - 1) as u32;
                    let p = image.get_pixel(px, py);
                    sum_r += p.0[0] as u64;
                    sum_g += p.0[1] as u64;
                    sum_b += p.0[2] as u64;
                    count += 1;
                }
            }
            if count == 0 {
                return None;
            }
            Some((
                (sum_r / count) as u8,
                (sum_g / count) as u8,
                (sum_b / count) as u8,
            ))
        } else {
            let p = image.get_pixel(x_rel as u32, y_rel as u32);
            Some((p.0[0], p.0[1], p.0[2]))
        }
    }
}

#[derive(Default)]
struct TickFrameCache {
    tick_ms: Option<u64>,
    frames: HashMap<String, CachedFrame>,
}

pub(crate) struct CachedFrame {
    image: image::RgbaImage,
    x: i32,
    y: i32,
}

pub struct CachedPixelSampler {
    cache: Mutex<TickFrameCache>,
}

impl CachedPixelSampler {
    pub fn new() -> Self {
        Self {
            cache: Mutex::new(TickFrameCache::default()),
        }
    }

    /// Try to get a cached frame image for the given monitor.
    /// Returns `None` if no frame has been captured for this monitor
    /// in the current tick.
    pub fn get_cached_monitor_image(&self, monitor: &str) -> Option<image::RgbaImage> {
        let cache = self.cache.lock().ok()?;
        let key = resolved_monitor_key(monitor)?;
        // Look up any cached frame whose key starts with this monitor's key.
        // The frame_key format is the monitor name, so a direct lookup works.
        cache.frames.get(&key).map(|frame| frame.image.clone())
    }

    /// Capture a monitor frame (or return cached), returning the full
    /// image and the monitor origin offset so the ROI provider can sample
    /// rectangular regions.
    pub fn ensure_monitor_frame(&self, monitor: &str) -> Option<(image::RgbaImage, i32, i32)> {
        let key = resolved_monitor_key(monitor)?;
        let mut cache = self.cache.lock().ok()?;
        if let Some(frame) = cache.frames.get(&key) {
            return Some((frame.image.clone(), frame.x, frame.y));
        }
        // Not cached yet — capture the full monitor.
        let frame = capture_monitor_full_frame(monitor)?;
        let image = frame.image.clone();
        let (x, y) = (frame.x, frame.y);
        cache.frames.insert(key, frame);
        Some((image, x, y))
    }
}

impl Default for CachedPixelSampler {
    fn default() -> Self {
        Self::new()
    }
}

impl PixelSampler for CachedPixelSampler {
    fn begin_tick(&self, tick_ms: u64) {
        if let Ok(mut cache) = self.cache.lock() {
            if cache.tick_ms != Some(tick_ms) {
                cache.tick_ms = Some(tick_ms);
                cache.frames.clear();
            }
        }
    }

    fn sample_rgb_abs(
        &self,
        monitor: &str,
        x_abs: i32,
        y_abs: i32,
        sample_mode: &str,
        sample_radius: u8,
    ) -> Option<(u8, u8, u8)> {
        let frame_key = pixel_frame_key(monitor, x_abs, y_abs)?;
        let mut cache = self.cache.lock().ok()?;
        if !cache.frames.contains_key(&frame_key) {
            let frame = capture_pixel_frame(monitor, x_abs, y_abs)?;
            cache.frames.insert(frame_key.clone(), frame);
        }
        let frame = cache.frames.get(&frame_key)?;
        let x_rel = x_abs - frame.x;
        let y_rel = y_abs - frame.y;
        sample_image_rgb(&frame.image, x_rel, y_rel, sample_mode, sample_radius)
    }
}

fn pixel_frame_key(monitor: &str, x_abs: i32, y_abs: i32) -> Option<String> {
    let requested = monitor.trim();
    if requested.is_empty() {
        let monitors = Monitor::all().ok()?;
        let selected = monitor_for_abs_point(&monitors, x_abs, y_abs)?;
        Some(monitor_name(selected))
    } else {
        resolved_monitor_key(requested)
    }
}

/// Resolve a monitor name (including "primary" / empty → primary monitor)
/// to a stable cache key.
fn resolved_monitor_key(monitor: &str) -> Option<String> {
    let requested = monitor.trim();
    if requested.is_empty() || requested.eq_ignore_ascii_case("primary") {
        let monitors = Monitor::all().ok()?;
        let primary = monitors.iter().find(|m| monitor_is_primary(m))?;
        Some(monitor_name(primary))
    } else {
        Some(requested.to_string())
    }
}

/// Capture the full monitor image for ROI-style sampling.
pub(crate) fn capture_monitor_full_frame(monitor: &str) -> Option<CachedFrame> {
    let monitors = Monitor::all().ok()?;
    let requested = monitor.trim();
    let selected = if requested.is_empty() || requested.eq_ignore_ascii_case("primary") {
        monitors.iter().find(|m| monitor_is_primary(m))?
    } else {
        let key = requested.to_lowercase();
        monitors
            .iter()
            .find(|m| monitor_name(m).to_lowercase() == key)?
    };
    let image = selected.capture_image().ok()?;
    Some(CachedFrame {
        image,
        x: monitor_x(selected),
        y: monitor_y(selected),
    })
}

fn capture_pixel_frame(monitor: &str, x_abs: i32, y_abs: i32) -> Option<CachedFrame> {
    let monitors = Monitor::all().ok()?;
    let requested = monitor.trim();
    let selected = if requested.is_empty() {
        monitor_for_abs_point(&monitors, x_abs, y_abs)?
    } else if requested.eq_ignore_ascii_case("primary") {
        monitors.iter().find(|m| monitor_is_primary(m))?
    } else {
        let key = requested.to_lowercase();
        monitors
            .iter()
            .find(|m| monitor_name(m).to_lowercase() == key)?
    };
    let image = selected.capture_image().ok()?;
    Some(CachedFrame {
        image,
        x: monitor_x(selected),
        y: monitor_y(selected),
    })
}

fn monitor_for_abs_point(monitors: &[Monitor], x_abs: i32, y_abs: i32) -> Option<&Monitor> {
    monitors
        .iter()
        .find(|m| {
            let mx = monitor_x(m);
            let my = monitor_y(m);
            let mw = monitor_w(m) as i32;
            let mh = monitor_h(m) as i32;
            x_abs >= mx && x_abs < mx + mw && y_abs >= my && y_abs < my + mh
        })
        .or_else(|| monitors.iter().find(|m| monitor_is_primary(m)))
        .or_else(|| monitors.first())
}

fn sample_image_rgb(
    image: &image::RgbaImage,
    x_rel: i32,
    y_rel: i32,
    sample_mode: &str,
    sample_radius: u8,
) -> Option<(u8, u8, u8)> {
    if x_rel < 0 || y_rel < 0 || x_rel >= image.width() as i32 || y_rel >= image.height() as i32 {
        return None;
    }

    if sample_mode == "mean_square" && sample_radius > 0 {
        let r = sample_radius as i32;
        let mut sum_r: u64 = 0;
        let mut sum_g: u64 = 0;
        let mut sum_b: u64 = 0;
        let mut count: u64 = 0;
        for dy in -r..=r {
            for dx in -r..=r {
                let px = (x_rel + dx).max(0).min(image.width() as i32 - 1) as u32;
                let py = (y_rel + dy).max(0).min(image.height() as i32 - 1) as u32;
                let p = image.get_pixel(px, py);
                sum_r += p.0[0] as u64;
                sum_g += p.0[1] as u64;
                sum_b += p.0[2] as u64;
                count += 1;
            }
        }
        if count == 0 {
            return None;
        }
        Some((
            (sum_r / count) as u8,
            (sum_g / count) as u8,
            (sum_b / count) as u8,
        ))
    } else {
        let p = image.get_pixel(x_rel as u32, y_rel as u32);
        Some((p.0[0], p.0[1], p.0[2]))
    }
}

// ===========================================================================
// 测试
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_capture_manager_new() {
        let cm = CaptureManager::new();
        assert!(cm.is_ok(), "xcap should enumerate monitors");
        let cm = cm.unwrap();
        assert!(!cm.monitors.is_empty(), "at least one monitor");
    }

    #[test]
    fn test_monitor_names() {
        let cm = CaptureManager::new().unwrap();
        let names = cm.monitor_names();
        assert!(!names.is_empty());
        println!("Monitors: {names:?}");
    }

    #[test]
    fn test_find_primary() {
        let cm = CaptureManager::new().unwrap();
        let m = cm.find_monitor("primary");
        assert!(m.is_some(), "should find primary monitor");
    }

    #[test]
    fn test_abs_to_rel() {
        let cm = CaptureManager::new().unwrap();
        let m = cm.find_monitor("primary").unwrap();
        let (rx, ry) = cm.abs_to_rel(monitor_x(m), monitor_y(m), "primary");
        assert_eq!((rx, ry), (0, 0));
    }

    #[test]
    fn test_sample_pixel() {
        let mut cm = CaptureManager::new().unwrap();
        let result = cm.sample_pixel("primary", 0, 0);
        println!("sample_pixel(0,0): {result:?}");
    }

    #[test]
    fn test_direct_sampler() {
        let sampler = DirectPixelSampler;
        let result = sampler.sample_rgb_abs("primary", 0, 0, "single", 0);
        println!("DirectPixelSampler sample: {result:?}");
    }
}
