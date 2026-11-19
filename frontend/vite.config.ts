// Vite builds and serves the app; the "test" part configures Vitest, which reuses
// the same setup so tests understand TypeScript, JSX and CSS imports exactly like the app.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, // the address the backend allows in its CORS setting (FRONTEND_ORIGIN)
  },
  test: {
    environment: "jsdom", // a fake browser (document, window) inside Node.js
    setupFiles: ["./src/test/setup.ts"],
    css: false, // tests check behavior, not styles
  },
});
