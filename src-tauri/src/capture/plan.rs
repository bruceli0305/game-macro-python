//! CapturePlan 构建器 — ProbeRequirements → CapturePlan

use crate::ast::compiler::ProbeRequirements;
use crate::capture::capturer::{CapturePlan, CaptureRegion};

pub fn build_plan(
    probes: &ProbeRequirements,
    point_positions: &[(&str, &str, i32, i32)],
    skill_pixel_positions: &[(&str, &str, i32, i32)],
) -> CapturePlan {
    let mut regions = Vec::new();

    for pid in &probes.point_ids {
        if let Some((_, monitor, vx, vy)) = point_positions.iter().find(|(id, _, _, _)| *id == pid)
        {
            regions.push(CaptureRegion {
                monitor_name: monitor.to_string(),
                x: *vx,
                y: *vy,
                width: 1,
                height: 1,
            });
        }
    }

    for sid in &probes.skill_pixel_ids {
        if let Some((_, monitor, vx, vy)) = skill_pixel_positions
            .iter()
            .find(|(id, _, _, _)| *id == sid)
        {
            regions.push(CaptureRegion {
                monitor_name: monitor.to_string(),
                x: *vx,
                y: *vy,
                width: 1,
                height: 1,
            });
        }
    }

    CapturePlan { regions }
}
