/** @type {import('next').NextConfig} */
// Single-origin deployment (Dockerfile at the repo root / Render): the browser calls /api/* on the
// same HTTPS origin and Next forwards it to the FastAPI process inside the container.
const internalApi = process.env.BIOQUEST_INTERNAL_API || "http://127.0.0.1:8000";
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${internalApi}/api/:path*` }];
  },
};

export default nextConfig;
