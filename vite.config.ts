import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig(async () => ({
  plugins: [vue(), tailwindcss()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? { protocol: "ws", host, port: 1421 }
      : undefined,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("naive-ui")) return "vendor-naive";
          if (id.includes("@tabler/icons-vue")) return "vendor-icons";
          if (id.includes("@codemirror") || id.includes("codemirror")) return "vendor-codemirror";
          if (id.includes("vue-draggable-plus") || id.includes("sortablejs")) return "vendor-dnd";
          if (id.includes("@tauri-apps")) return "vendor-tauri";
          if (id.includes("vue") || id.includes("pinia")) return "vendor-vue";
          return "vendor";
        },
      },
    },
    chunkSizeWarningLimit: 650,
  },
}));
