/**
 * The setup wizard records how it ended on the server (plan D18), so
 * "Skip for now" keeps the wizard away from every browser — first run is
 * "no board has a usable output AND the wizard was neither completed nor
 * skipped" — not only the one whose localStorage remembers it.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { SetupWizard } from "@/components/wizard";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

describe("SetupWizard", () => {
  it("records a skipped wizard server-side", async () => {
    const recorded: unknown[] = [];
    server.use(
      http.put("/api/settings/wizard", async ({ request }) => {
        const body = await request.json();
        recorded.push(body);
        return HttpResponse.json(body);
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SetupWizard />
      </QueryClientProvider>,
    );
    // The first step's "add a display later" (plan D18); the Vestaboard
    // step's "Skip for now" is covered in setup-wizard-choose-output.test.tsx.
    await userEvent.click(await screen.findByRole("button", { name: /I'll add a display later/ }));
    await waitFor(() => expect(recorded).toEqual([{ state: "skipped" }]));
  });
});
