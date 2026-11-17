import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { SilenceImminentBanner } from "@/components/silence-imminent-banner";

import { server } from "./mocks/server";

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
function draw(extra: Record<string, unknown> = {}) {
  server.use(
    http.get("/api/silence-status", () =>
      HttpResponse.json({
        enabled: true,
        active: false,
        mode: "page",
        page_id: "page-2",
        seconds_until_next_change: 720,
        ...extra,
      }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SilenceImminentBanner />
    </QueryClientProvider>,
  );
  return client;
}
describe("Silence Schedule starts soon", () => {
  it("shows the drawn 12 min warning and only Edit Silence Schedule", async () => {
    draw();
    const banner = await screen.findByTestId("silence-imminent-banner");
    await waitFor(() => expect(banner).toHaveTextContent(/12 min/));
    expect(banner).toHaveTextContent(/Silence Schedule starts at/);
    await waitFor(() => expect(banner).toHaveTextContent(/holds Custom Template/));
    expect(screen.getByRole("link", { name: "Edit Silence Schedule" })).toHaveAttribute("href", "/schedule");
    expect(screen.queryByRole("button", { name: /Dismiss|Switch now/ })).not.toBeInTheDocument();
  });
  it.each(["freeze", "indicator"])("warns for %s without claiming a page switch", async (mode) => {
    draw({ mode });
    const banner = await screen.findByTestId("silence-imminent-banner");
    expect(banner).toHaveTextContent(/New messages wait/);
    expect(banner).not.toHaveTextContent(/holds Custom/);
  });
  it.each([
    { enabled: false },
    { active: true },
    { seconds_until_next_change: 901 },
    { seconds_until_next_change: 0 },
    { seconds_until_next_change: -1 },
    { seconds_until_next_change: null },
  ])("does not invent an imminent event for %j", async (extra) => {
    const client = draw(extra);
    await waitFor(() => expect(client.getQueryData(["silenceStatus"])).toBeDefined());
    // Settle the real query; absence alone before it completes is not a test.
    await waitFor(() => expect(screen.queryByTestId("silence-imminent-banner")).not.toBeInTheDocument());
  });
});
