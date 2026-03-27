import type { StorybookConfig } from "@storybook/nextjs";
import type { Configuration } from "webpack";
import NodePolyfillPlugin from "node-polyfill-webpack-plugin";

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
    // Replace the NodePolyfillPlugin added by @storybook/nextjs with one that
    // excludes the `crypto` polyfill. This prevents crypto-browserify (and its
    // transitive elliptic dependency) from being bundled into Storybook builds.
    // None of the stories in this project use the Node.js `crypto` module.
    webpackConfig.plugins = (webpackConfig.plugins ?? []).filter(
      (p) => p?.constructor?.name !== "NodePolyfillPlugin"
    );
    webpackConfig.plugins.push(
      new NodePolyfillPlugin({ excludeAliases: ["crypto"] })
    );
    return webpackConfig;
  },
};

export default config;

