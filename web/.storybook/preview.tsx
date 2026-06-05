import "../src/app/globals.css";

import type { Preview } from "@storybook/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { ThemeProvider, useTheme } from "next-themes";
import { useEffect } from "react";

import de from "../messages/de.json";
import en from "../messages/en.json";
import es from "../messages/es.json";
import fr from "../messages/fr.json";
import it from "../messages/it.json";
import ja from "../messages/ja.json";
import ko from "../messages/ko.json";
import nl from "../messages/nl.json";
import pl from "../messages/pl.json";
import pt from "../messages/pt.json";
import ru from "../messages/ru.json";
import sv from "../messages/sv.json";
import tr from "../messages/tr.json";
import zh from "../messages/zh.json";
import { type Locale, localeNames, locales } from "../src/i18n/config";

const messages: Record<Locale, typeof en> = { en, es, fr, de, it, pt, nl, pl, ru, sv, tr, ja, ko, zh };

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: Infinity,
    },
  },
});

function ThemeSync({ theme }: { theme: string }) {
  const { setTheme } = useTheme();
  useEffect(() => setTheme(theme), [theme, setTheme]);
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
    nextjs: {
      appDirectory: true,
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
      const theme = context.globals.theme || "dark";
      const locale = (context.globals.locale || "en") as Locale;
      return (
        <NextIntlClientProvider locale={locale} messages={messages[locale]}>
          <QueryClientProvider client={queryClient}>
            <ThemeProvider
              attribute="class"
              defaultTheme={theme}
              enableSystem={false}
              forcedTheme={theme}
              disableTransitionOnChange
            >
              <ThemeSync theme={theme} />
              <main className="min-h-screen bg-background text-foreground p-8">
                <Story />
              </main>
            </ThemeProvider>
          </QueryClientProvider>
        </NextIntlClientProvider>
      );
    },
  ],
};

export default preview;
