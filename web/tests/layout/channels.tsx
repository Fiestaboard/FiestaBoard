import "../../app/globals.css";

import { PageLayout } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";

import { ReleaseChannelCard } from "@/components/settings/release-channel";

// Isolated Settings → System section, with real kit controls and API calls.
if (new URLSearchParams(location.search).get("theme") === "dark") document.documentElement.classList.add("dark");
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <PageLayout>
      <ReleaseChannelCard />
    </PageLayout>
  </QueryClientProvider>,
);
