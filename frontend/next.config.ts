import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  
  // Empty turbopack config to silence warning
  turbopack: {},
};

export default nextConfig;
