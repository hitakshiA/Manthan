import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    // Split the biggest vendor deps into their own chunks so cold-cache
    // visitors don't pay for them on the marketing-landing first-paint,
    // and so they stay cache-stable across our deploys (their hash
    // doesn't move when our app code changes).
    rolldownOptions: {
      output: {
        advancedChunks: {
          groups: [
            // React + react-router - tiny, but everything loads it.
            {
              name: "react",
              test: /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/,
            },
            // motion (~150KB+) - used in animation-heavy pages; isolate.
            { name: "motion", test: /[\\/]node_modules[\\/]motion[\\/]/ },
            // @clerk/* - signed-in surface only.
            { name: "clerk", test: /[\\/]node_modules[\\/]@clerk[\\/]/ },
            // simple-icons - even with named imports the data lookup
            // tables are sizable; keep in its own chunk so it doesn't
            // get pulled into the landing chunk by accidental shared
            // imports.
            {
              name: "simple-icons",
              test: /[\\/]node_modules[\\/]simple-icons[\\/]/,
            },
            // lucide-react - icon set used in ~26 files; tree-shakes
            // per-import but the runtime helper code is shared.
            { name: "lucide", test: /[\\/]node_modules[\\/]lucide-react[\\/]/ },
          ],
        },
      },
    },
  },
});
