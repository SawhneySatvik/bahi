import type { NextConfig } from "next";

// All /api/* and /health calls proxy to the FastAPI server — the browser never
// needs CORS, and deployment just points BAHI_API_URL at the hosted API.
const API_URL = process.env.BAHI_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
};

export default nextConfig;
