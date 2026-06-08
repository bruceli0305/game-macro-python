//! 像素扫描器 — 在 CapturePlan 上执行采样

use crate::ast::evaluator::PixelSampler;
use crate::capture::capturer::{CapturePlan, DirectPixelSampler};

pub type SampledRgb = Option<(u8, u8, u8)>;
pub type IndexedSample = (usize, SampledRgb);

pub struct PixelScanner;

impl PixelScanner {
    pub fn new() -> Self {
        Self
    }

    pub fn sample_all(&self, plan: &CapturePlan) -> Vec<IndexedSample> {
        let sampler = DirectPixelSampler;
        plan.regions
            .iter()
            .enumerate()
            .map(|(i, region)| {
                let rgb =
                    sampler.sample_rgb_abs(&region.monitor_name, region.x, region.y, "single", 0);
                (i, rgb)
            })
            .collect()
    }
}

impl Default for PixelScanner {
    fn default() -> Self {
        Self::new()
    }
}
