import js from "@eslint/js";
import prettierConfig from "eslint-config-prettier";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import tseslint from "typescript-eslint";

export default [
  {
    ignores: [".docusaurus/**", "build/**", "node_modules/**", "static/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx,js,jsx,mjs,cjs}"],
    plugins: {
      react,
      "react-hooks": reactHooks,
      "simple-import-sort": simpleImportSort,
    },
    languageOptions: {
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        fetch: "readonly",
        process: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        sessionStorage: "readonly",
        localStorage: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        Headers: "readonly",
        Request: "readonly",
        Response: "readonly",
      },
    },
    settings: {
      react: { version: "19" },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
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
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  // Design-system enforcement, mirroring web/eslint.config.mjs: the site's own
  // React renders @fiestaboard/ui components, not raw HTML. Allowlisted leaves
  // (svg, canvas, iframe, img, br, em, small, kbd, pre, figure, figcaption, dl,
  // dt, dd, input, hr, blockquote) are simply not listed here.
  //
  // Scoped to src/components and src/pages on purpose. src/theme holds swizzled
  // Docusaurus components, which must mirror upstream's markup and Infima class
  // names to keep their behaviour (`.menu__list-item`, `.pagination-nav__link`,
  // `.clean-btn`); forcing primitives there would break the theme rather than
  // align it. Those files use DS components where the markup is genuinely ours.
  {
    files: ["src/components/**/*.tsx", "src/pages/**/*.tsx"],
    rules: {
      "react/forbid-elements": [
        "error",
        {
          forbid: [
            { element: "div", message: "Use Flex/Stack/Grid for layout, or Box (@fiestaboard/ui)" },
            { element: "span", message: 'Use Text as="span" (@fiestaboard/ui)' },
            { element: "p", message: "Use Text (@fiestaboard/ui)" },
            // `h1` is intentionally absent. The web app forbids it in favour of
            // `PageHeader`, but that is app chrome; FiestaUI's `Heading` covers
            // h2-h4 only, so a docs/marketing page's single h1 has no primitive
            // to move to and keeps its own element.
            { element: "h2", message: "Use Heading level={2} (@fiestaboard/ui)" },
            { element: "h3", message: "Use Heading level={3} (@fiestaboard/ui)" },
            { element: "h4", message: "Use Heading level={4} (@fiestaboard/ui)" },
            { element: "h5", message: "Use Heading (@fiestaboard/ui)" },
            { element: "h6", message: "Use Heading (@fiestaboard/ui)" },
            { element: "ul", message: "Use List (@fiestaboard/ui)" },
            { element: "ol", message: 'Use List as="ol" (@fiestaboard/ui)' },
            { element: "li", message: "Use ListItem (@fiestaboard/ui)" },
            { element: "section", message: 'Use Box as="section" (@fiestaboard/ui)' },
            { element: "main", message: 'Use Box as="main" (@fiestaboard/ui)' },
            { element: "header", message: 'Use Box as="header" (@fiestaboard/ui)' },
            { element: "footer", message: 'Use Box as="footer" (@fiestaboard/ui)' },
            { element: "nav", message: 'Use Box as="nav" (@fiestaboard/ui)' },
            { element: "form", message: 'Use Box as="form" (@fiestaboard/ui)' },
            { element: "table", message: "Use Table (@fiestaboard/ui)" },
            { element: "thead", message: "Use TableHeader (@fiestaboard/ui)" },
            { element: "tbody", message: "Use TableBody (@fiestaboard/ui)" },
            { element: "tr", message: "Use TableRow (@fiestaboard/ui)" },
            { element: "th", message: "Use TableHead (@fiestaboard/ui)" },
            { element: "td", message: "Use TableCell (@fiestaboard/ui)" },
            { element: "button", message: "Use Button (@fiestaboard/ui)" },
            { element: "a", message: "Use TextLink, or Docusaurus Link for navigation (@fiestaboard/ui)" },
            { element: "code", message: "Use Code (@fiestaboard/ui)" },
            { element: "strong", message: 'Use Text as="span" weight="semibold" (@fiestaboard/ui)' },
          ],
        },
      ],
    },
  },
  prettierConfig,
];
