import type { StorybookConfig } from "@storybook/nextjs";
import type { Configuration } from "webpack";

const config: StorybookConfig = {
  stories: [
    "../src/**/*.mdx",
    "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  addons: [
    "@storybook/addon-a11y",
  ],
  framework: {
    name: "@storybook/nextjs",
    options: {},
  },
  staticDirs: ["../public"],
  typescript: {
    reactDocgen: "react-docgen-typescript",
  },
  webpackFinal: async (webpackConfig: Configuration) => {
    // Disable the crypto fallback polyfill injected by @storybook/nextjs via
    // node-polyfill-webpack-plugin. Setting it to false tells webpack to omit
    // the crypto-browserify bundle (which carries a vulnerable elliptic
    // dependency). None of the stories in this project use Node.js `crypto`.
    if (webpackConfig.resolve) {
      webpackConfig.resolve.fallback = {
        ...webpackConfig.resolve.fallback,
        crypto: false,
      };
    }
    return webpackConfig;
  },
};

export default config;

