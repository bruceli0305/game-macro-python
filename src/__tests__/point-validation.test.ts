import { describe, expect, it } from "vitest";
import {
  firstPointDraftError,
  normalizePointDraft,
  validatePointDraft,
} from "../utils/point-validation";
import type { Point } from "../types/point";

function point(id: string): Point {
  return {
    id,
    name: id,
    monitor: "primary",
    vx: 10,
    vy: 20,
    color: { r: 10, g: 20, b: 30 },
    tolerance: 20,
    sample: { mode: "single", radius: 0 },
    captured_at: "2026-06-08T00:00:00.000Z",
    note: "",
  };
}

describe("point draft validation", () => {
  it("rejects empty point ids", () => {
    expect(
      validatePointDraft(point(" "), { existingPoints: [], editingIndex: -1 })
    ).toBe("点位 ID 不能为空");
  });

  it("rejects duplicate point ids", () => {
    expect(
      validatePointDraft(point("boss"), {
        existingPoints: [point("boss")],
        editingIndex: -1,
      })
    ).toBe("点位 ID 重复：boss");
  });

  it("rejects tolerance outside 0-255", () => {
    const draft = point("boss");
    draft.tolerance = 300;

    expect(firstPointDraftError([draft])).toBe("点位容差必须在 0-255 之间：boss");
  });

  it("rejects unsupported sample modes", () => {
    const draft = point("boss");
    draft.sample.mode = "median";

    expect(validatePointDraft(draft, { existingPoints: [], editingIndex: -1 })).toBe(
      "点位采样模式必须是 single 或 mean_square：boss"
    );
  });

  it("rejects sample radius outside 0-255", () => {
    const draft = point("boss");
    draft.sample.radius = 300;

    expect(validatePointDraft(draft, { existingPoints: [], editingIndex: -1 })).toBe(
      "点位采样半径必须在 0-255 之间：boss"
    );
  });

  it("allows negative coordinates for monitors left of primary", () => {
    const draft = point("left-monitor");
    draft.vx = -120;

    expect(validatePointDraft(draft, { existingPoints: [], editingIndex: -1 })).toBeNull();
  });

  it("normalizes text fields, monitor defaults, and numeric fields", () => {
    const draft = point(" boss ");
    draft.name = " Boss Point ";
    draft.monitor = " ";
    draft.vx = 10.4;
    draft.vy = 20.6;
    draft.color = { r: 300, g: -10, b: 20.4 };
    draft.tolerance = 22.6;
    draft.sample.mode = " single ";
    draft.sample.radius = 1.6;
    draft.note = " #0a141e ";

    expect(normalizePointDraft(draft)).toMatchObject({
      id: "boss",
      name: "Boss Point",
      monitor: "primary",
      vx: 10,
      vy: 21,
      color: { r: 255, g: 0, b: 20 },
      tolerance: 23,
      sample: { mode: "single", radius: 2 },
      note: "#0a141e",
    });
  });
});
