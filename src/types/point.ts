// 与 Rust models/point.rs 对齐
import type { ColorRGB, SampleConfig } from "./skill";

export interface Point {
  id: string;
  name: string;
  monitor: string;
  vx: number;
  vy: number;
  color: ColorRGB;
  tolerance: number;
  sample: SampleConfig;
  captured_at: string;
  note: string;
}

export interface PointsFile {
  schema_version: number;
  points: Point[];
}
