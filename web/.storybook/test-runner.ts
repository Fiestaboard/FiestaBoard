import { getStoryContext, type TestRunnerConfig } from "@storybook/test-runner";
import { checkA11y, configureAxe, injectAxe } from "axe-playwright";

type Size = { width: number; height: number };

/** The runner's own page size, kept while a story borrows another one. */
let borrowedFrom: Size | null = null;

const config: TestRunnerConfig = {
  async preVisit(page, context) {
    await injectAxe(page);
    // A story can set `parameters.testViewport` ({ width, height }) to have
    // its play function and the a11y pass run at that size — the phone
    // stories assert the phone layout. The size is given back after the
    // visit, so every other story runs exactly as before.
    const storyContext = await getStoryContext(page, context);
    const viewport = storyContext.parameters?.testViewport as Size | undefined;
    if (viewport) {
      borrowedFrom = page.viewportSize();
      await page.setViewportSize(viewport);
    }
  },
  async postVisit(page) {
    await configureAxe(page, {
      rules: [
        { id: "page-has-heading-one", enabled: false },
        { id: "heading-order", enabled: false },
        { id: "color-contrast-enhanced", enabled: false },
      ],
    });

    try {
      await checkA11y(page, "#storybook-root", {
        detailedReport: true,
        detailedReportOptions: {
          html: true,
        },
      });
    } finally {
      if (borrowedFrom) {
        await page.setViewportSize(borrowedFrom);
        borrowedFrom = null;
      }
    }
  },
};

export default config;
