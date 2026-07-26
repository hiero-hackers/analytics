/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app deploys next to the data it renders: CI copies web/dist, the data
// API, and the chart PNGs into one Pages site, so all URLs are base-relative.
// In dev, /data and /charts proxy to the repo's static outputs server
// (`python -m http.server 8642 -d outputs`, the existing dashboard-preview
// launch config) — same layout, no copying.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/data": "http://localhost:8642",
      "/charts": "http://localhost:8642",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});
