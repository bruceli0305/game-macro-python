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

  return { active, previewX, previewY, previewR, previewG, previewB, previewHex, setPreview, startSession, endSession };
});
