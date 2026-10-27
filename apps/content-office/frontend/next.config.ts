import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.OFFICE_API_URL || "http://127.0.0.1:8510"}/api/:path*`,
      },
    ];
  },
};
export default config;
