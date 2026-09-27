import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.dirname(fileURLToPath(import.meta.url)),
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8765/api/:path*" }];
  },
};

export default nextConfig;
