import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // Read VITE_* variables from the repo-root .env (shared with the backend).
  envDir: "..",
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:5000" },
  },
});
