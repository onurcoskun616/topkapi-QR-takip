import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  server: {
    host: true,
    port: 5175,
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["apple-touch-icon.png"],
      manifest: {
        name: "Topkapı Yoklama",
        short_name: "Yoklama",
        description: "Topkapı Okulları personel giriş/çıkış uygulaması",
        lang: "tr",
        theme_color: "#0b1f3a",
        background_color: "#0b1f3a",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // The app shell is cached for offline launch; API calls are never
        // cached (attendance must always hit the live server).
        navigateFallbackDenylist: [/^\/api/],
        globPatterns: ["**/*.{js,css,html,png,svg,ico}"],
        // Pull our push/notificationclick handlers into the generated SW
        // without switching away from the default precaching strategy.
        importScripts: ["/push-sw.js"],
      },
    }),
  ],
});
