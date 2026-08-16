/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output keeps the runtime image small — see Dockerfile.
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
