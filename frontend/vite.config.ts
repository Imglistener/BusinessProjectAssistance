import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Read VITE_* variables from the repo-root .env (shared with the backend).
  envDir: "..",
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:5000" },
  },
});
