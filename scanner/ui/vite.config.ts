import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";
import path from "path";

export default defineConfig({
  plugins: [
    react(),
    legacy({
      targets: ["Chrome >= 60", "Firefox >= 60", "Safari >= 12"],
      additionalLegacyPolyfills: ["regenerator-runtime/runtime"],
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: {
    target: "es2015",  // Chrome 79 지원
  },
  esbuild: {
    target: "es2015",  // 개발 모드에서도 적용
  },
  server: {
    port: 5173,
    proxy: {
      // 브라우저 → Vite dev 서버 → (프록시) → 로컬 exe
      "/scanner": {
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/scanner/, ""),
      },
      "/downloader": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/downloader/, ""),
      },
    },
  },
});
