import "../../app/globals.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, Link, Outlet, RouterProvider, useNavigate, useParams } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { MainContent } from "@/components/main-content";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";
import { SidebarProvider } from "@/components/sidebar-context";
import { Toaster } from "@/components/ui/sonner";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

import { PagesSection } from "../../app/routes/pages";
import NewPage from "../../app/routes/pages.new";

// The editor inside the real app chrome (BB-E-3, -4): the nav rail, the main
// column and the Pages section around the production editor shell, so the
// spec measures what the editor gets of the window. The spec supplies every
// hub response through Playwright routes (creator-ide-hub.ts).
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
const params = new URLSearchParams(window.location.search);
const theme = params.get("theme") === "dark" ? "dark" : "light";
localStorage.setItem("theme", theme);
localStorage.setItem("fiestaboard_current_board", "kitchen-board");

function Shell() {
  return (
    <SidebarProvider>
      <NavigationSidebar />
      <MainContent>
        <Outlet />
      </MainContent>
      <Toaster />
    </SidebarProvider>
  );
}

function PagesList() {
  return (
    <PagesSection>
      <Link to="/pages/edit/kitchen-morning">Open Kitchen morning</Link>
    </PagesSection>
  );
}

function Editor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  return (
    <PagesSection>
      <PageEditorShell pageId={id} onClose={() => navigate("/pages")} onSave={() => {}} />
    </PagesSection>
  );
}

const router = createMemoryRouter(
  [
    {
      element: <Shell />,
      children: [
        { path: "/pages", element: <PagesList /> },
        { path: "/pages/edit/:id", element: <Editor /> },
        {
          path: "/pages/new",
          element: (
            <PagesSection>
              <NewPage />
            </PagesSection>
          ),
        },
      ],
    },
  ],
  { initialEntries: [params.get("path") ?? "/pages/edit/kitchen-morning"] },
);

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider defaultTheme={theme}>
          <CurrentBoardProvider>
            <PageEditorBridgeProvider>
              <GlobalAiPanelProvider>
                <RouterProvider router={router} />
              </GlobalAiPanelProvider>
            </PageEditorBridgeProvider>
          </CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  </I18nextProvider>,
);
