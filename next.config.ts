import type { NextConfig } from "next";

// Keep framework headers quieter when this is eventually deployed.
const nextConfig: NextConfig = {
  poweredByHeader: false,
};

export default nextConfig;
