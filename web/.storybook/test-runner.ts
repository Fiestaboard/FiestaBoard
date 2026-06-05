import type { TestRunnerConfig } from "@storybook/test-runner";
import { checkA11y, configureAxe, injectAxe } from "axe-playwright";

const config: TestRunnerConfig = {
  async preVisit(page) {
    await injectAxe(page);
  },
  async postVisit(page) {
    await configureAxe(page, {
      rules: [
        { id: "page-has-heading-one", enabled: false },
        { id: "heading-order", enabled: false },
        { id: "color-contrast-enhanced", enabled: false },
      ],
    });

    await checkA11y(page, "#storybook-root", {
      detailedReport: true,
      detailedReportOptions: {
        html: true,
      },
    });
  },
};

export default config;
