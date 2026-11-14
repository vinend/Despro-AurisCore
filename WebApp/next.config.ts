import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  distDir: process.env.AURISCORE_NEXT_DIST_DIR ?? ".next",
  // The LAN launcher supplies only the selected interface address.
  allowedDevOrigins: (process.env.AURISCORE_ALLOWED_DEV_ORIGINS ?? "")
    .split(",").map(host => host.trim()).filter(Boolean),
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
};

export default nextConfig;
