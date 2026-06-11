import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEngine } from "../composables/useEngine";
import { isProfileNotFoundError, useProfile } from "../composables/useProfile";
import { useEngineStore } from "../stores/engine";
import { useProfileStore } from "../stores/profile";

const { invokeMock, listenMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: listenMock,
}));

function installTauriRuntime() {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {},
  });
  Object.defineProperty(globalThis.window, "__TAURI_INTERNALS__", {
    configurable: true,
    value: { invoke: vi.fn() },
  });
}

describe("composable regressions", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    installTauriRuntime();
    invokeMock.mockReset();
    listenMock.mockReset();
    listenMock.mockResolvedValue(vi.fn());
  });

  it("does not mark the engine running until a backend event or runtime snapshot arrives", async () => {
    invokeMock.mockResolvedValue("started");

    await useEngine().start();

    expect(invokeMock).toHaveBeenCalledWith("engine_start");
    expect(useEngineStore().isRunning).toBe(false);
  });

  it("classifies only explicit missing-profile errors as create-default cases", () => {
    expect(isProfileNotFoundError({ code: "config", message: "Profile not found: raid" }, "raid"))
      .toBe(true);
    expect(isProfileNotFoundError({ code: "toml_deserialize", message: "Profile not found: raid" }, "raid"))
      .toBe(false);
    expect(isProfileNotFoundError({ code: "config", message: "TOML deserialize error" }, "raid"))
      .toBe(false);
  });

  it("creates a default profile only when the backend reports the profile is missing", async () => {
    invokeMock.mockRejectedValue({ code: "config", message: "Profile not found: raid" });

    const profile = await useProfile().loadOrCreateProfile("raid");

    expect(profile.meta.profile_id).toBe("raid");
    expect(useProfileStore().profile?.meta.profile_id).toBe("raid");
  });

  it("propagates corrupt profile load errors instead of replacing user data", async () => {
    const error = { code: "toml_deserialize", message: "invalid TOML" };
    invokeMock.mockRejectedValue(error);

    await expect(useProfile().loadOrCreateProfile("default")).rejects.toEqual(error);
    expect(useProfileStore().profile).toBeNull();
  });
});
