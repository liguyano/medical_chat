import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: [
    "192.168.144.1",
    "lt.frp-gap.com",
    "hohofrontend.cpolar.top",
  ],
};

export default nextConfig;
