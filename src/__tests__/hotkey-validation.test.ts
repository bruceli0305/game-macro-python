import { describe, expect, it } from "vitest";
import { createDefaultProfile } from "../composables/useProfile";
import { validateProfileForSave } from "../utils/profile-validation";

describe("hotkey validation", () => {
  it("rejects conflicting global hotkeys before save", () => {
    const profile = createDefaultProfile();
    profile.base.pick.confirm_hotkey = "f9";
    profile.base.exec.toggle_hotkey = "F9";

    expect(validateProfileForSave(profile).map((item) => item.message)).toContain(
      "取色确认热键和引擎启停热键不能相同：F9"
    );
  });
});
