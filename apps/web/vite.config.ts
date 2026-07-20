/** Vite 配置：开发服务器、API 代理与 OpenCut Classic alias。 */



import path from "path";

import { fileURLToPath } from "url";

import { defineConfig } from "vite";

import react from "@vitejs/plugin-react";

import wasm from "vite-plugin-wasm";

import topLevelAwait from "vite-plugin-top-level-await";



const __dirname = path.dirname(fileURLToPath(import.meta.url));

const opencutRoot = path.resolve(__dirname, "src/editor/opencut");



export default defineConfig({

  plugins: [react(), wasm(), topLevelAwait()],

  resolve: {

    alias: {

      "@opencut": opencutRoot,

      "next/link": path.resolve(opencutRoot, "shims/next-link.tsx"),

      "next/image": path.resolve(opencutRoot, "shims/next-image.tsx"),

      "next/navigation": path.resolve(opencutRoot, "shims/next-navigation.ts"),

    },

  },

  build: {

    rollupOptions: {

      output: {

        manualChunks(id) {

          if (id.includes("node_modules/opencut-wasm")) return "opencut-wasm";

          if (id.includes("node_modules/@huggingface/transformers")) return "transformers";

          if (id.includes("src/editor/opencut/services/transcription/worker")) return "transformers";

          if (id.includes("src/editor/opencut/core") || id.includes("src/editor/opencut/timeline")) {

            return "opencut-core";

          }

        },

      },

    },

  },

  server: {
    // 0.0.0.0：同时可被 127.0.0.1 与 localhost（含 Chromium 解析）访问，避免桌面壳白屏
    host: true,
    port: 5173,
    strictPort: true,
    // 桌面壳由 Electron 承载 UI；禁止 Vite 自动打开系统浏览器
    open: false,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "http://localhost:8000", ws: true },
    },
  },

  optimizeDeps: {

    exclude: ["opencut-wasm"],

  },

});


