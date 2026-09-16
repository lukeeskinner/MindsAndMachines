import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  plugins: [tailwindcss()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
