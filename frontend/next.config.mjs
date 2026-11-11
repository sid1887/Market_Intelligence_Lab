/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["lightweight-charts"],
  async rewrites() {
    const backend = process.env.BACKEND_API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
