import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: ["@storybook/addon-a11y"],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  staticDirs: ["../public"],
  typescript: {
    reactDocgen: "react-docgen-typescript",
  },
  /**
   * Storybook auto-discovers the project `vite.config.ts`, which includes
   * `@react-router/dev/vite`. That plugin asserts on a real RR7 config
   * file shape and throws `Error: The React Router Vite plugin requires
   * the use of a Vite config file` when Storybook tries to build the
   * preview. Storybook isn't an RR7 app — strip the plugin (and the
   * vite-plugin-pwa one, for the same reason) before Storybook spins up
   * Vite. The Tailwind plugin stays so component stories keep their
   * styling.
   */
  async viteFinal(viteConfig) {
    const filtered = (viteConfig.plugins ?? []).flat(Infinity).filter((p) => {
      if (!p || typeof p !== "object" || !("name" in p)) return true;
      const name = (p as { name?: string }).name ?? "";
      return !name.startsWith("react-router") && !name.startsWith("vite-plugin-pwa");
    });
    return {
      ...viteConfig,
      plugins: filtered,
    };
  },
};

export default config;
