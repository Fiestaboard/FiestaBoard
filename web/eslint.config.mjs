import prettierConfig from "eslint-config-prettier";
import i18nextPlugin from "eslint-plugin-i18next";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import tseslint from "typescript-eslint";

const REACT_VERSION = "19";

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
  {
    ignores: [
      "node_modules/**",
      ".react-router/**",
      "build/**",
      "dist/**",
      "out/**",
      "public/**",
      "storybook-static/**",
      "coverage/**",
      "test-results/**",
      "playwright-report/**",
    ],
  },
  // typescript-eslint's recommended rule set — replaces what
  // `eslint-config-next/typescript` was contributing before the
  // migration. This must come BEFORE the project-level rule block
  // so the TS parser and plugin are available everywhere downstream.
  ...tseslint.configs.recommended,
  {
    // React + JSX recommended rules (replaces eslint-config-next's curated set).
    files: ["**/*.{ts,tsx,js,jsx,mjs,cjs}"],
    plugins: {
      react: reactPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
      "simple-import-sort": simpleImportSort,
    },
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: "latest",
        sourceType: "module",
      },
    },
    settings: {
      react: { version: REACT_VERSION },
    },
    rules: {
      // React 19 + React Compiler readiness rules. Warnings (not errors) so
      // they're visible but don't block CI; tighten in a follow-up.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/immutability": "warn",
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      // Strict TypeScript + general correctness rules for AI-written code
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "prefer-const": "error",
      "no-var": "error",
      eqeqeq: ["error", "smart"],
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
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
      "no-console": "off",
    },
  },
  // Disable any ESLint formatting rules that would conflict with Prettier.
  // Must come last so it overrides anything earlier.
  prettierConfig,
];

export default eslintConfig;
