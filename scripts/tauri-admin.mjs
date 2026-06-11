import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const tauriPackage = require.resolve("@tauri-apps/cli/package.json");
const tauriBin = join(dirname(tauriPackage), "tauri.js");

const child = spawn(process.execPath, [tauriBin, ...process.argv.slice(2)], {
  env: {
    ...process.env,
    GAME_MACRO_ADMIN_MANIFEST: "1",
  },
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 1);
});

child.on("error", (error) => {
  console.error(error);
  process.exit(1);
});
