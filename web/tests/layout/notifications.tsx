import "../../app/globals.css";
import "@/i18n/i18next";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { MainContent } from "@/components/main-content";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { SidebarProvider } from "@/components/sidebar-context";
import { WizardProvider } from "@/components/wizard-provider";
import { ThemeProvider } from "@/hooks/use-theme";

import SettingsPage from "../../app/routes/settings";

// The real route, navigation and published kit. Only browser push and hub HTTP
// boundaries are substituted by the Playwright spec; no notification UI fake.
const params = new URLSearchParams(location.search);
const theme = params.get("theme") ?? "light";
// Static-theme evidence starts in that palette. ThemeProvider remains live,
// but its first effect must not create a light-to-dark color transition
// while axe samples the page's foreground and background separately.
document.documentElement.classList.toggle("dark", theme === "dark");
const client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false } },
});
localStorage.setItem("fiestaboard_wizard_complete", "true");
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[params.get("route") ?? "/settings/notifications"]}>
      <ThemeProvider attribute="class" defaultTheme={theme as "light" | "dark"}>
        <GlobalAiPanelProvider>
          <SidebarProvider>
            <CurrentBoardProvider>
              <WizardProvider>
                <NavigationSidebar />
                <MainContent>
                  <Routes>
                    <Route path="/settings/:section?" element={<SettingsPage />} />
                  </Routes>
                </MainContent>
              </WizardProvider>
            </CurrentBoardProvider>
          </SidebarProvider>
        </GlobalAiPanelProvider>
      </ThemeProvider>
    </MemoryRouter>
  </QueryClientProvider>,
);
