import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    include: ["src/__tests__/**/*.test.{ts,tsx}"],
    // ScheduleEntryForm renders 1440 SelectItems (one per minute of the day).
    // jsdom creating ~2880 Radix UI nodes per render exceeds the 5000ms default.
    testTimeout: 20000,
    environmentOptions: {
      jsdom: {
        resources: "usable",
      },
    },
    coverage: {
      provider: "v8",
      include: [
        "src/lib/**",
        "src/hooks/**",
        "src/components/board-display.tsx",
        "src/components/active-page-display.tsx",
        "src/components/navigation-sidebar.tsx",
        "src/components/service-status.tsx",
        "src/components/service-controls.tsx",
        "src/components/config-display.tsx",
        "src/components/general-settings.tsx",
        "src/components/silence-mode-status.tsx",
        "src/components/theme-toggle.tsx",
        "src/components/day-selector.tsx",
        "src/components/time-picker.tsx",
        "src/components/timezone-picker.tsx",
        "src/components/page-grid-selector.tsx",
        "src/components/page-picker-dialog.tsx",
        "src/components/schedule-entry-form.tsx",
        "src/components/live-output.tsx",
        "src/components/output-target-selector.tsx",
        "src/components/notification-display.tsx",
        "src/components/language-selector.tsx",
        "src/i18n/config.ts",
      ],
      exclude: [
        "src/__tests__/**",
        "**/*.stories.tsx",
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
      reporter: ["text", "text-summary", "lcov"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
