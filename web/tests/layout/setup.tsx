import "../../app/globals.css";
import "@/i18n/i18next";

import { PageHeader, PageLayout } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { SignedInDevices } from "@/components/settings/signed-in-devices";

const params = new URLSearchParams(location.search);
if (params.get("theme") === "dark") document.documentElement.classList.add("dark");
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><QueryClientProvider client={client}>
    <PageLayout><PageHeader title="Settings" description="Account" /><SignedInDevices /></PageLayout>
  </QueryClientProvider></BrowserRouter>,
);
