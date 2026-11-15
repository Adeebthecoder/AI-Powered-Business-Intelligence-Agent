// Vite settings for the React frontend.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Every request that starts with /api is passed on to the FastAPI backend.
    // This way the frontend code never needs to know the backend address.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    // Plotly is a big library. This only silences the size warning.
    chunkSizeWarningLimit: 6000,
  },
});
