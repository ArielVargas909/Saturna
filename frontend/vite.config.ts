/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";

function normalizeBase(raw?: string): string {
  if (!raw || raw === "/") return "/";
  const withLeading = raw.startsWith("/") ? raw : `/${raw}`;
  return withLeading.endsWith("/") ? withLeading : `${withLeading}/`;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  const base = normalizeBase(env.VITE_BASE_PATH);

  return {
    base,
    plugins: [
      react(),
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["logo-icon.svg", "logo-full.svg", "logo-white.svg", "apple-touch-icon.png"],
        manifest: {
          name: "Saturna",
          short_name: "Saturna",
          description: "Entregas inteligentes, retiros en segundos",
          lang: "es-BO",
          theme_color: "#0B1445",
          background_color: "#0B1445",
          display: "standalone",
          scope: base,
          start_url: base,
          icons: [
            { src: "logo-icon.svg", sizes: "any", type: "image/svg+xml" },
            { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
            { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
            { src: "pwa-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          ],
        },
        workbox: {
          // La app carga sin conexión; las llamadas a la API nunca se cachean (datos siempre frescos).
          navigateFallbackDenylist: [/^\/api/],
          globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        },
      }),
    ],
    server: { port: 5173 },
    test: { environment: "node" },
  };
});
