import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import i18nextPlugin from "eslint-plugin-i18next";

// Pin React version explicitly to avoid context.getFilename() deprecation in flat config
const coreWebVitalsFixed = coreWebVitals.map((config) =>
  config.settings?.react
    ? { ...config, settings: { ...config.settings, react: { ...config.settings.react, version: "19" } } }
    : config
);

// Wrap eslint-plugin-i18next rules with a getSourceCode shim for flat config compatibility
const i18nextPluginCompat = {
  ...i18nextPlugin,
  rules: Object.fromEntries(
    Object.entries(i18nextPlugin.rules).map(([name, rule]) => [
      name,
      {
        ...rule,
        create(context) {
          const patchedContext = Object.assign(Object.create(context), {
            getSourceCode: () => context.sourceCode,
          });
          return rule.create(patchedContext);
        },
      },
    ])
  ),
};

const eslintConfig = [
  ...coreWebVitalsFixed,
  ...nextTypescript,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      "public/**",
      "storybook-static/**",
    ],
  },
  {
    // Strict TypeScript rules - enforce type safety
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { 
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
      }],
    },
  },
  {
    // i18n: catch hardcoded user-facing strings in JSX that should be translated
    plugins: {
      i18next: i18nextPluginCompat,
    },
    rules: {
      "i18next/no-literal-string": ["warn", {
        mode: "jsx-text-only",
        "jsx-attributes": {
          include: ["title", "placeholder", "alt", "aria-label"],
        },
        words: {
          exclude: [
            "FiestaBoard",
            "Vestaboard",
            "•",
            "&middot;",
          ],
        },
        "should-validate-template": false,
      }],
    },
  },
];

export default eslintConfig;
