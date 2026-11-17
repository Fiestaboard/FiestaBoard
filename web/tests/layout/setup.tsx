import "../../app/globals.css";
import "@/i18n/i18next";

import { PageHeader, PageLayout } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { SignedInDevices } from "@/components/settings/signed-in-devices";
import { SetupWizard } from "@/components/wizard/setup-wizard";

import Activate from "../../app/routes/activate";
import ResetPassword from "../../app/routes/reset-password";

const params = new URLSearchParams(location.search);
if (params.get("theme") === "dark") document.documentElement.classList.add("dark");
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <QueryClientProvider client={client}>
      {params.get("mode") === "wizard" ? (
        <SetupWizard />
      ) : params.get("mode") === "activate" ? (
        <Activate />
      ) : params.get("mode") === "reset" ? (
        <ResetPassword />
      ) : (
        <PageLayout>
          <PageHeader icon={Settings} title="Settings" description="Account" />
          <SignedInDevices />
        </PageLayout>
      )}
    </QueryClientProvider>
  </BrowserRouter>,
);
