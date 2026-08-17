import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  /**
   * The build's own timestamp, rendered in the sidebar.
   *
   * Six rounds of owner testing produced reports of fixes "not working" that were
   * verified working minutes earlier, and every one turned out to be a browser holding
   * an older bundle — a tab open across a rebuild, or a server never restarted. There was
   * no way for either side to tell, so each round spent its first hour re-diagnosing a
   * fixed bug. A visible stamp settles it in one glance: if it does not match the build
   * that was just made, nothing about behaviour is worth discussing yet.
   */
  define: {
    __BUILD_ID__: JSON.stringify(new Date().toISOString().slice(0, 16).replace("T", " ")),
  },
  build: {
    /**
     * A budget, not Vite's default guess.
     *
     * The default 500 kB fired on every build and so meant nothing. Measured
     * 2026-08-14: the entry chunk is 533 kB raw / **159 kB gzip**, and it was inspected
     * rather than assumed — no stage code, no map styles, no tour art are in it, which
     * is route splitting working. What *is* in it is react-dom, react-router and
     * TanStack Query, plus `i18n/copy.json` at 137 kB and the landing hero, both of
     * which the entry route genuinely needs.
     *
     * 560 is therefore "roughly what the framework plus the catalogue costs, and no
     * room for a stage to leak back in". If this warns, something has escaped a lazy
     * boundary — which is a signal worth reading, unlike the default.
     *
     * Splitting the copy catalogue by language would halve it, and is deliberately not
     * done: `artifact 027` requires both languages in one payload so a language switch
     * never refetches, and importing it `as const` is what type-checks the keys.
     */
    chunkSizeWarningLimit: 560,
  },
  server: {
    fs: { allow: [".."] },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        timeout: 120_000,
        proxyTimeout: 120_000,
      },
    },
  },
  test: { environment: "node" },
});
