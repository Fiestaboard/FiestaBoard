import "../../app/globals.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

// The spec supplies every API response through Playwright routes. Keep the
// production editor, preview, toolbar and provider tree intact in this fixture.
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const theme = new URLSearchParams(window.location.search).get("theme") === "dark" ? "dark" : "light";
localStorage.setItem("theme", theme);
localStorage.setItem("fiestaboard_current_board", "kitchen-board");

createRoot(document.getElementById("root")!).render(
  <MemoryRouter>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <ConfigOverridesProvider>
          <ThemeProvider defaultTheme={theme}>
            <CurrentBoardProvider>
              <main className="content-root min-h-screen bg-background text-foreground">
                <div className="mx-auto max-w-screen-xl p-0 lg:p-6">
                  <PageBuilder pageId="kitchen-morning" embedded onClose={() => {}} />
                </div>
              </main>
            </CurrentBoardProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </QueryClientProvider>
    </I18nextProvider>
  </MemoryRouter>,
);
