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

// Web 2.9 (04b): the spec picks the page (`?page=`) and supplies every API
// response through Playwright routes. Keep the
// production editor, preview, toolbar and provider tree intact in this fixture.
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const params = new URLSearchParams(window.location.search);
const theme = params.get("theme") === "dark" ? "dark" : "light";
const pageId = params.get("page") ?? "kitchen-morning";
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
                {/* Mirror the route shell headings above the embedded editor title. */}
                <h1 className="sr-only">Pages</h1>
                <h2 className="sr-only">Page editor</h2>
                <div className="mx-auto max-w-screen-xl p-0 lg:p-6">
                  <PageBuilder pageId={pageId} embedded onClose={() => {}} />
                </div>
              </main>
            </CurrentBoardProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </QueryClientProvider>
    </I18nextProvider>
  </MemoryRouter>,
);
