import "../../app/globals.css";
import "@/i18n/i18next";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { ConnectPhone } from "@/components/settings/connect-phone";
import { SetupWizard } from "@/components/wizard/setup-wizard";
import { WizardProvider } from "@/components/wizard-provider";
import { queryKeys } from "@/hooks/use-board";
import { api } from "@/lib/api";

import Home from "../../app/routes/home";

const params = new URLSearchParams(location.search);
const mode = params.get("mode") ?? "home";
document.documentElement.classList.toggle("dark", params.get("theme") === "dark");
// Prevent the first-run takeover while rendering the real empty Home route.
localStorage.setItem("fiestaboard_wizard_complete", "true");
localStorage.removeItem("fiestaboard_wizard_progress");
if (mode === "tv" || mode === "led") {
  localStorage.setItem(
    "fiestaboard_wizard_progress",
    JSON.stringify({
      currentStep: 2,
      outputId: mode === "tv" ? "fiestapanel" : "led-display",
      outputName: mode === "tv" ? "FiestaPanel TV" : "LED display (Pixoo / TC001)",
    }),
  );
}
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
function PhoneFixture() {
  const [open, setOpen] = useState(true);
  return <ConnectPhone open={open} onClose={() => setOpen(false)} onChanged={() => undefined} />;
}
async function mount() {
  // Home's shell normally has this fleet read in flight before the route.
  // Await the intercepted real API to avoid flashing a configured-board state.
  if (mode === "home")
    await client.ensureQueryData({ queryKey: queryKeys.boardSettings, queryFn: api.getBoardSettings });
  createRoot(document.getElementById("root")!).render(
    <BrowserRouter>
      <QueryClientProvider client={client}>
        {mode === "tv" || mode === "led" ? (
          <SetupWizard />
        ) : mode === "qr" ? (
          <PhoneFixture />
        ) : (
          <CurrentBoardProvider>
            <WizardProvider>
              <Home />
            </WizardProvider>
          </CurrentBoardProvider>
        )}
      </QueryClientProvider>
    </BrowserRouter>,
  );
}
void mount();
