import type { NextConfig } from "next";

// The browser only talks to this app; /api/* is proxied to the FastAPI backend, so the backend
// needs no CORS setup.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
