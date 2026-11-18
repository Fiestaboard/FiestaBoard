import "../../app/globals.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, RouterProvider } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

// The spec supplies every hub response through Playwright routes. The real
// editor shell mounts, so the lazily loaded Creator IDE, the editor header
// seam and the Explorer slot are all the production ones.
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const theme = new URLSearchParams(window.location.search).get("theme") === "dark" ? "dark" : "light";
localStorage.setItem("theme", theme);
localStorage.setItem("fiestaboard_current_board", "kitchen-board");

function Editor() {
  return (
    <main className="content-root flex h-screen min-h-0 flex-col bg-background text-foreground">
      <h1 className="sr-only">Pages</h1>
      <h2 className="sr-only">Kitchen morning</h2>
      <PageEditorShell pageId="kitchen-morning" onClose={() => {}} onSave={() => {}} />
    </main>
  );
}

const router = createMemoryRouter([{ path: "*", element: <Editor /> }], {
  initialEntries: ["/pages/edit/kitchen-morning"],
});

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider defaultTheme={theme}>
          <CurrentBoardProvider>
            <PageEditorBridgeProvider>
              <RouterProvider router={router} />
            </PageEditorBridgeProvider>
          </CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  </I18nextProvider>,
);
