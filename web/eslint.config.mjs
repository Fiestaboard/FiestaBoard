import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
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
      get i18next() {
        return require("eslint-plugin-i18next");
      },
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
