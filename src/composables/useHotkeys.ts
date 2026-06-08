// 全局热键：配置驱动的引擎启停和取色确认。

import { ref } from "vue";
import { isRegistered, register, unregister } from "@tauri-apps/plugin-global-shortcut";
import { useEngine } from "./useEngine";
import { useEnginePreflight } from "./useEnginePreflight";
import { DEFAULT_PROFILE_NAME, useProfile } from "./useProfile";

type AppMessageType = "success" | "error" | "warning" | "info";

const DEFAULT_TOGGLE_HOTKEY = "F9";
const DEFAULT_PICK_HOTKEY = "F8";

export interface HotkeyDiagnosticsResult {
  toggle_hotkey: string;
  pick_hotkey: string;
  toggle_registered: boolean;
  pick_registered: boolean;
  toggle_callback_count: number;
  pick_callback_count: number;
  last_toggle_callback_at: string | null;
  last_pick_callback_at: string | null;
  conflict: boolean;
}

const callbackStats = {
  toggleCount: 0,
  pickCount: 0,
  lastToggleAt: null as string | null,
  lastPickAt: null as string | null,
};

function notify(type: AppMessageType, content: string) {
  window.dispatchEvent(new CustomEvent("app:message", { detail: { type, content } }));
}

function normalizeHotkey(value: string | undefined, fallback: string): string {
  const hotkey = value?.trim();
  return hotkey ? hotkey.toUpperCase() : fallback;
}

export function useHotkeys() {
  const { start, stop, store } = useEngine();
  const { validateEngineStart } = useEnginePreflight();
  const { loadOrCreateProfile } = useProfile();
  const lastToggle = ref(0);
  const registeredToggleHotkey = ref<string | null>(null);
  const registeredPickHotkey = ref<string | null>(null);

  async function configuredHotkeys() {
    const profile = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    return {
      toggle: normalizeHotkey(profile.base.exec.toggle_hotkey, DEFAULT_TOGGLE_HOTKEY),
      pick: normalizeHotkey(profile.base.pick.confirm_hotkey, DEFAULT_PICK_HOTKEY),
    };
  }

  async function registerHotkey(hotkey: string, handler: () => Promise<void>): Promise<boolean> {
    if (await isRegistered(hotkey)) {
      console.warn(`global shortcut already registered: ${hotkey}`);
      return false;
    }
    await register(hotkey, handler);
    return true;
  }

  async function setup(): Promise<boolean> {
    await teardown();

    let hotkeys = {
      toggle: DEFAULT_TOGGLE_HOTKEY,
      pick: DEFAULT_PICK_HOTKEY,
    };
    try {
      hotkeys = await configuredHotkeys();
    } catch (error) {
      console.warn("load hotkey config failed, using defaults:", error);
    }

    if (hotkeys.toggle === hotkeys.pick) {
      notify("error", `取色确认热键和引擎启停热键不能相同：${hotkeys.toggle}`);
      return false;
    }

    try {
      const registered = await registerHotkey(hotkeys.toggle, async () => {
        const now = Date.now();
        if (now - lastToggle.value < 500) return;
        lastToggle.value = now;
        callbackStats.toggleCount += 1;
        callbackStats.lastToggleAt = new Date(now).toISOString();

        if (store.isRunning) {
          await stop();
          notify("info", "引擎已停止");
          return;
        }

        const error = await validateEngineStart();
        if (error) {
          console.warn("engine preflight failed:", error);
          notify("error", error);
          return;
        }

        await start();
        notify("success", "引擎已启动");
      });
      if (registered) {
        registeredToggleHotkey.value = hotkeys.toggle;
        console.log(`engine toggle hotkey registered: ${hotkeys.toggle}`);
      }
    } catch (error) {
      console.warn(`${hotkeys.toggle} registration failed:`, error);
    }

    try {
      const registered = await registerHotkey(hotkeys.pick, async () => {
        callbackStats.pickCount += 1;
        callbackStats.lastPickAt = new Date().toISOString();
        window.dispatchEvent(new CustomEvent("picker:capture"));
      });
      if (registered) {
        registeredPickHotkey.value = hotkeys.pick;
        console.log(`color capture hotkey registered: ${hotkeys.pick}`);
      }
    } catch (error) {
      console.warn(`${hotkeys.pick} registration failed:`, error);
    }

    return (
      registeredToggleHotkey.value === hotkeys.toggle &&
      registeredPickHotkey.value === hotkeys.pick
    );
  }

  async function teardown() {
    if (registeredToggleHotkey.value) {
      try {
        await unregister(registeredToggleHotkey.value);
      } catch {
        // ignore
      }
      registeredToggleHotkey.value = null;
    }

    if (registeredPickHotkey.value) {
      try {
        await unregister(registeredPickHotkey.value);
      } catch {
        // ignore
      }
      registeredPickHotkey.value = null;
    }
  }

  async function reload() {
    const ok = await setup();
    if (ok) {
      notify("success", "全局热键已更新");
    } else {
      notify("warning", "全局热键未完全注册，请检查是否被其他程序占用");
    }
  }

  async function diagnostics(): Promise<HotkeyDiagnosticsResult> {
    const hotkeys = await configuredHotkeys();
    return {
      toggle_hotkey: hotkeys.toggle,
      pick_hotkey: hotkeys.pick,
      toggle_registered: await isRegistered(hotkeys.toggle),
      pick_registered: await isRegistered(hotkeys.pick),
      toggle_callback_count: callbackStats.toggleCount,
      pick_callback_count: callbackStats.pickCount,
      last_toggle_callback_at: callbackStats.lastToggleAt,
      last_pick_callback_at: callbackStats.lastPickAt,
      conflict: hotkeys.toggle === hotkeys.pick,
    };
  }

  return { setup, teardown, reload, diagnostics };
}
