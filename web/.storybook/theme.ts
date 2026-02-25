import { create } from "@storybook/theming/create";

export default create({
  base: "dark",
  brandTitle: "FiestaBoard UI Components",
  brandUrl: "https://github.com/Fiestaboard/FiestaBoard",
  brandTarget: "_self",

  // UI
  appBg: "#0a0a0a",
  appContentBg: "#1a1a1a",
  appBorderColor: "#2a2a2a",
  appBorderRadius: 8,

  // Typography
  fontBase: '"Inter", sans-serif',
  fontCode: '"Fira Code", monospace',

  // Text colors
  textColor: "#f0f0f0",
  textInverseColor: "#0a0a0a",

  // Toolbar default and active colors
  barTextColor: "#9ca3af",
  barSelectedColor: "#f0f0f0",
  barBg: "#0a0a0a",

  // Form colors
  inputBg: "#1a1a1a",
  inputBorder: "#2a2a2a",
  inputTextColor: "#f0f0f0",
  inputBorderRadius: 6,
});

