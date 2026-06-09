import { describe, expect, it } from "vitest";
import {
  buildCompleteDetectionExpr,
  buildStartDetectionExpr,
  firstPointId,
} from "../utils/detection-templates";

describe("detection templates", () => {
  it("builds start detection expressions from presets", () => {
    expect(buildStartDetectionExpr("none", "bar", 12)).toBeNull();
    expect(buildStartDetectionExpr("immediate", "bar", 12)).toEqual({
      type: "const",
      value: true,
    });
    expect(buildStartDetectionExpr("cast_bar_changed", "bar", 12)).toEqual({
      type: "cast_bar_changed",
      point_id: "bar",
      tolerance: 12,
    });
    expect(buildStartDetectionExpr("cast_bar_roi_changed", "bar", 12)).toEqual({
      type: "cast_bar_roi_changed",
    });
    expect(buildStartDetectionExpr("cast_bar_roi_border_visible", "bar", 12)).toEqual({
      type: "cast_bar_roi_border_visible",
    });
  });

  it("builds complete detection expressions from presets", () => {
    expect(buildCompleteDetectionExpr("timer", "sk1", "bar", 8)).toBeNull();
    expect(buildCompleteDetectionExpr("cast_bar_changed", "sk1", "bar", 8)).toEqual({
      type: "cast_bar_changed",
      point_id: "bar",
      tolerance: 8,
    });
    expect(buildCompleteDetectionExpr("cast_bar_roi_gone", "sk1", "bar", 8)).toEqual({
      type: "cast_bar_roi_gone",
    });
    expect(buildCompleteDetectionExpr("skill_pixel", "sk1", "bar", 8)).toEqual({
      type: "pixel_skill",
      skill_id: "sk1",
      tolerance: 8,
    });
    expect(buildCompleteDetectionExpr("skill_pixel_black", "sk1", "bar", 8)).toEqual({
      type: "pixel_skill_black",
      skill_id: "sk1",
      tolerance: 8,
    });
  });

  it("chooses the first point as the template default", () => {
    expect(firstPointId([{ id: "bar" }, { id: "other" }])).toBe("bar");
    expect(firstPointId([])).toBe("");
  });
});
