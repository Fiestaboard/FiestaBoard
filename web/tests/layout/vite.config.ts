import { realpathSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const root = fileURLToPath(new URL("../../", import.meta.url));
export default defineConfig({
  root,
  cacheDir: "./.vite-layout",
  server: { fs: { allow: [root, realpathSync(path.join(root, "node_modules"))] } },
  resolve: { alias: { "@": path.join(root, "src") } },
  plugins: [tailwindcss(), react()],
});
