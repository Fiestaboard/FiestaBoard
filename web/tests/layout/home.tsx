import "../../app/globals.css";
import "../../src/i18n/i18next";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { WizardProvider } from "@/components/wizard-provider";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import Home from "../../app/routes/home";

const dark = new URLSearchParams(location.search).get("theme") === "dark";
localStorage.setItem("fiestaboard_wizard_complete", "true");
localStorage.setItem("fiestaboard_site_animations", "false");
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme={dark ? "dark" : "light"}>
          <CurrentBoardProvider>
            <WizardProvider>
              <main>
                <Home />
              </main>
            </WizardProvider>
          </CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  </BrowserRouter>,
);
