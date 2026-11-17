import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // Sin el botón flotante de dev-tools: ensucia la esquina de la consola.
  devIndicators: false,
};

export default nextConfig;
