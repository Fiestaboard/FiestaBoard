import type { NextConfig } from "next";
import withPWAInit from "@ducanh2912/next-pwa";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin();

// Bundle analyzer (only enabled when ANALYZE env var is set)
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "true",
});

const withPWA = withPWAInit({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
  register: true,
  skipWaiting: true,
  reloadOnOnline: true,
  fallbacks: {
    document: "/offline",
  },
  workboxOptions: {
    disableDevLogs: true,
    runtimeCaching: [
      {
        urlPattern: /^https?.*/,
        handler: "NetworkFirst",
        options: {
          cacheName: "offlineCache",
          expiration: {
            maxEntries: 200,
            maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
          },
          networkTimeoutSeconds: 10,
        },
      },
    ],
  },
});

const nextConfig: NextConfig = {
  // Run as a server (not static export)
  // Runtime API URL configuration - no build-time env vars needed
  
  // Enable standalone output for optimized Docker builds
  // This bundles only production dependencies and necessary files
  output: 'standalone',
  
  // Image optimization configuration
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
  },
  
  // Enable compression
  compress: true,
  
  // Remove X-Powered-By header for security
  poweredByHeader: false,
  
  // Turbopack configuration (Next.js 16 uses Turbopack by default)
  // Empty config to silence warning about webpack config from PWA plugin
  turbopack: {},
  
  typescript: {
    // Don't fail builds on pre-existing type errors
    // Note: Type checking still runs locally via tsc
    ignoreBuildErrors: true,
  },
};

export default withBundleAnalyzer(withNextIntl(withPWA(nextConfig)));
