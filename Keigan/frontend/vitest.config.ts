import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

// A separate file from vite.config.ts so the build keeps its own plugins and chunking. The tests cover pure logic (protocol, reducer,
// polling decisions, text builders), so they run in Node without a DOM.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
