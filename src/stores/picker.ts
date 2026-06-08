import { defineStore } from "pinia";
import { ref } from "vue";

export const usePickerStore = defineStore("picker", () => {
  const active = ref(false);
  const previewX = ref(0);
  const previewY = ref(0);
  const previewR = ref(0);
  const previewG = ref(0);
  const previewB = ref(0);
  const previewHex = ref("#000000");
  const captureRequestCount = ref(0);
  const captureSuccessCount = ref(0);
  const captureFailureCount = ref(0);
  const captureIgnoredCount = ref(0);
  const lastCaptureContext = ref("");
  const lastCaptureStatus = ref<"idle" | "success" | "failed" | "ignored">("idle");
  const lastCaptureAt = ref<string | null>(null);
  const lastCaptureMessage = ref("");

  function setPreview(x: number, y: number, r: number, g: number, b: number, hex: string) {
    previewX.value = x;
    previewY.value = y;
    previewR.value = r;
    previewG.value = g;
    previewB.value = b;
    previewHex.value = hex;
  }

  function startSession() {
    active.value = true;
  }

  function endSession() {
    active.value = false;
  }

  function recordCaptureRequest(context: string) {
    captureRequestCount.value += 1;
    lastCaptureContext.value = context;
    lastCaptureAt.value = new Date().toISOString();
    lastCaptureStatus.value = "idle";
    lastCaptureMessage.value = "capture requested";
  }

  function recordCaptureSuccess(context: string, message: string) {
    captureSuccessCount.value += 1;
    lastCaptureContext.value = context;
    lastCaptureAt.value = new Date().toISOString();
    lastCaptureStatus.value = "success";
    lastCaptureMessage.value = message;
  }

  function recordCaptureFailure(context: string, message: string) {
    captureFailureCount.value += 1;
    lastCaptureContext.value = context;
    lastCaptureAt.value = new Date().toISOString();
    lastCaptureStatus.value = "failed";
    lastCaptureMessage.value = message;
  }

  function recordCaptureIgnored(context: string, message: string) {
    captureIgnoredCount.value += 1;
    lastCaptureContext.value = context;
    lastCaptureAt.value = new Date().toISOString();
    lastCaptureStatus.value = "ignored";
    lastCaptureMessage.value = message;
  }

  return {
    active,
    previewX,
    previewY,
    previewR,
    previewG,
    previewB,
    previewHex,
    captureRequestCount,
    captureSuccessCount,
    captureFailureCount,
    captureIgnoredCount,
    lastCaptureContext,
    lastCaptureStatus,
    lastCaptureAt,
    lastCaptureMessage,
    setPreview,
    startSession,
    endSession,
    recordCaptureRequest,
    recordCaptureSuccess,
    recordCaptureFailure,
    recordCaptureIgnored,
  };
});
