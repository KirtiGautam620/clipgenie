import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, forward /api requests to the FastAPI server
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.CLIPGENIE_API || "http://127.0.0.1:8000" },   // CLIPGENIE_API: point at another backend (testing)
  },
});
