import "../src/app/globals.css";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

import type { Preview } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { MemoryRouter } from "react-router";

import { ThemeProvider, useTheme } from "../src/hooks/use-theme";
import { type Locale, localeNames, locales } from "../src/i18n/config";
import i18n from "../src/i18n/i18next";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: Infinity,
    },
  },
});

function ThemeSync({ theme }: { theme: "light" | "dark" }) {
  const { setTheme } = useTheme();
  useEffect(() => setTheme(theme), [theme, setTheme]);
  return null;
}

function LocaleSync({ locale }: { locale: Locale }) {
  const { i18n: rrtI18n } = useTranslation();
  useEffect(() => {
    void rrtI18n.changeLanguage(locale);
  }, [locale, rrtI18n]);
  return null;
}

const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Theme for components",
      toolbar: {
        title: "Theme",
        icon: "paintbrush",
        items: [
          { value: "dark", icon: "moon", title: "Dark" },
          { value: "light", icon: "sun", title: "Light" },
        ],
        dynamicTitle: true,
      },
    },
    locale: {
      description: "Locale for i18n",
      toolbar: {
        title: "Locale",
        icon: "globe",
        items: locales.map((loc) => ({
          value: loc,
          title: localeNames[loc],
          right: loc.toUpperCase(),
        })),
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    theme: "dark",
    locale: "en",
  },
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      config: {
        rules: [
          { id: "page-has-heading-one", enabled: false },
          { id: "heading-order", enabled: false },
          { id: "color-contrast-enhanced", enabled: true },
        ],
      },
    },
  },
  decorators: [
    (Story, context) => {
      const theme = (context.globals.theme || "dark") as "light" | "dark";
      const locale = (context.globals.locale || "en") as Locale;
      return (
        // MemoryRouter so stories that call useLocation / useNavigate via the
        // compat shim (e.g. NavigationSidebar) have a Router context. Stories
        // don't actually navigate; "/" is fine as the initial entry.
        <MemoryRouter initialEntries={["/"]}>
          <I18nextProvider i18n={i18n}>
            <QueryClientProvider client={queryClient}>
              <ThemeProvider defaultTheme={theme}>
                <ThemeSync theme={theme} />
                <LocaleSync locale={locale} />
                <main className="min-h-screen bg-background text-foreground p-8">
                  <Story />
                </main>
              </ThemeProvider>
            </QueryClientProvider>
          </I18nextProvider>
        </MemoryRouter>
      );
    },
  ],
};

export default preview;
