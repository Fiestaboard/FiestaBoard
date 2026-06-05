/** @type {import('next').NextConfig} */
const nextConfig = {
  // Simplified config for Storybook - no standalone output
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

module.exports = nextConfig;
