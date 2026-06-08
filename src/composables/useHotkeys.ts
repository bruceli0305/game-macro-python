// 全局热键 — F9 启停引擎, F8 取色

import { ref } from "vue";
import { register, unregister, isRegistered } from "@tauri-apps/plugin-global-shortcut";
import { useEngine } from "./useEngine";

export function useHotkeys() {
  const { start, stop, store } = useEngine();
  const lastToggle = ref(0);

  async function setup() {
    // F9: 启停引擎
    try {
      if (!(await isRegistered("F9"))) {
        await register("F9", async () => {
          const now = Date.now();
          if (now - lastToggle.value < 500) return;
          lastToggle.value = now;
          if (store.isRunning) { await stop(); }
          else { await start(); }
        });
        console.log("F9 已注册 (启停引擎)");
      }
    } catch (e) { console.warn("F9 注册失败:", e); }

    // F8: 取色 — 通过自定义事件通知 PointsPage
    try {
      if (!(await isRegistered("F8"))) {
        await register("F8", async () => {
          window.dispatchEvent(new CustomEvent("picker:capture"));
        });
        console.log("F8 已注册 (取色)");
      }
    } catch (e) { console.warn("F8 注册失败:", e); }
  }

  async function teardown() {
    try { await unregister("F9"); } catch { /* ignore */ }
    try { await unregister("F8"); } catch { /* ignore */ }
  }

  return { setup, teardown };
}
