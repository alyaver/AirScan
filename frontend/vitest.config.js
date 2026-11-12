import { defineConfig, mergeConfig } from "vite";
import viteConfig from "./vite.config.js";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.js",
    },
  }),
);