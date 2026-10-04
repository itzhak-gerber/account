/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the backend runs separately; proxy keeps everything same-origin
// (needed later for the secure session cookie).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": backendUrl,
      "/auth": backendUrl,
      "/mcp": backendUrl,
      "/.well-known/oauth-protected-resource": backendUrl,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
