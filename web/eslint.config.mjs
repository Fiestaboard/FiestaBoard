import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import prettierConfig from "eslint-config-prettier";
import i18nextPlugin from "eslint-plugin-i18next";
import simpleImportSort from "eslint-plugin-simple-import-sort";

// Explicit React version to avoid context.getFilename() deprecation in flat config mode
// (eslint-plugin-react's version detection calls getFilename which was removed in ESLint 9+)
const REACT_VERSION = "19";

const coreWebVitalsConfigured = coreWebVitals.map((config) =>
  config.settings?.react
    ? { ...config, settings: { ...config.settings, react: { ...config.settings.react, version: REACT_VERSION } } }
    : config,
);

// Wrap eslint-plugin-i18next rules with a getSourceCode shim for flat config compatibility
// (eslint-plugin-i18next uses the legacy context.getSourceCode() API removed in ESLint 9+)
const i18nextPluginFlatConfigAdapter = {
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
    ]),
  ),
};

const eslintConfig = [
  ...coreWebVitalsConfigured,
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
      "coverage/**",
      "test-results/**",
      "playwright-report/**",
    ],
  },
  {
    // Strict TypeScript + general correctness rules for AI-written code
    plugins: {
      "simple-import-sort": simpleImportSort,
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "separate-type-imports" },
      ],
      "prefer-const": "error",
      "no-var": "error",
      eqeqeq: ["error", "smart"],
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
      // React Compiler readiness rules from Next 16 / eslint-plugin-react-hooks v6.
      // These surface real issues but classifying every existing setState-in-effect
      // as an error would balloon this PR into a behavioral refactor. Keep them on
      // as warnings so they're visible but don't block CI; tighten in a follow-up.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/immutability": "warn",
    },
  },
  {
    // i18n: catch hardcoded user-facing strings in JSX that should be translated
    plugins: {
      i18next: i18nextPluginFlatConfigAdapter,
    },
    rules: {
      "i18next/no-literal-string": [
        "warn",
        {
          mode: "jsx-text-only",
          "jsx-attributes": {
            include: ["title", "placeholder", "alt", "aria-label"],
          },
          words: {
            exclude: ["FiestaBoard", "Vestaboard", "•", "&middot;"],
          },
          "should-validate-template": false,
        },
      ],
    },
  },
  {
    // Tests legitimately use `any` for mocks and may define fixtures (Playwright)
    // they don't always consume. Don't let strict src rules bleed in here.
    files: [
      "**/__tests__/**",
      "**/tests/**",
      "**/*.spec.{ts,tsx}",
      "**/*.test.{ts,tsx}",
      "**/*.stories.{ts,tsx}",
      "vitest.config.{ts,mts}",
      "playwright.config.{ts,mts}",
    ],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          args: "none",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "no-console": "off",
    },
  },
  // Disable any ESLint formatting rules that would conflict with Prettier.
  // Must come last so it overrides anything earlier.
  prettierConfig,
];

export default eslintConfig;
