import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { usePickerStore } from "../stores/picker";

describe("picker store capture counters", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("records capture request, success, failure, and ignored states", () => {
    const store = usePickerStore();

    store.recordCaptureRequest("skills.skill");
    expect(store.captureRequestCount).toBe(1);
    expect(store.lastCaptureStatus).toBe("idle");
    expect(store.lastCaptureContext).toBe("skills.skill");
    expect(store.lastCaptureMessage).toBe("capture requested");

    store.recordCaptureSuccess("skills.skill", "primary (10,20) #112233");
    expect(store.captureSuccessCount).toBe(1);
    expect(store.lastCaptureStatus).toBe("success");
    expect(store.lastCaptureMessage).toBe("primary (10,20) #112233");

    store.recordCaptureFailure("skills.ammo:0", "capture_at_cursor returned empty result");
    expect(store.captureFailureCount).toBe(1);
    expect(store.lastCaptureStatus).toBe("failed");
    expect(store.lastCaptureContext).toBe("skills.ammo:0");

    store.recordCaptureIgnored("points.point", "debounced");
    expect(store.captureIgnoredCount).toBe(1);
    expect(store.lastCaptureStatus).toBe("ignored");
    expect(store.lastCaptureContext).toBe("points.point");
  });
});
