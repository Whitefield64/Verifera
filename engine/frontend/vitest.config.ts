import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Mirrors the "@/*" path alias in tsconfig.json. Without it, only type-only
// imports resolve under vitest (they get erased), and the first value import
// through the alias fails at run time.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});
