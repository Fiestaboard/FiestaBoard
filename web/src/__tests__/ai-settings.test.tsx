import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

import { AiSettings } from "@/components/settings/ai-settings";

const API_BASE = "/api";

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("AiSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the section title and the privacy notice", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    expect(await screen.findByText("AI Providers")).toBeInTheDocument();
    expect(
      screen.getByText(/sent directly to the provider you configure/i),
    ).toBeInTheDocument();
  });

  it("shows an empty state when no providers are configured", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    expect(
      await screen.findByText(/no providers configured yet/i),
    ).toBeInTheDocument();
  });

  it("can add a new provider row and reveal the model tag input", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    await screen.findByText(/no providers configured yet/i);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    expect(screen.getByLabelText(/^Name$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("openai/gpt-4o-mini")).toBeInTheDocument();
  });

  it("preserves the api_key mask when re-saving without changes", async () => {
    // Server returns a configured provider with masked key.
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "Test",
              base_url: "https://example.test/v1",
              api_key: "***",
              models: ["test-model"],
              default_model: "test-model",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );

    let receivedBody: Record<string, unknown> | null = null;
    server.use(
      http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(receivedBody);
      }),
    );

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Change the provider name to dirty the draft, then save.
    const nameInput = await screen.findByLabelText(/^Name$/);
    await user.clear(nameInput);
    await user.type(nameInput, "My OpenRouter");

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(receivedBody).not.toBeNull();
    });
    // The masked api_key MUST be sent back as-is so the backend
    // preserves the stored secret.
    const providers = (receivedBody as Record<string, unknown>)[
      "providers"
    ] as Array<{ api_key: string; name: string }>;
    expect(providers).toHaveLength(1);
    expect(providers[0].api_key).toBe("***");
    expect(providers[0].name).toBe("My OpenRouter");
  });

  it("test connection button calls /settings/ai/test", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "Test",
              base_url: "https://example.test/v1",
              api_key: "***",
              models: ["test-model"],
              default_model: "test-model",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );
    let testCalled = false;
    server.use(
      http.post(`${API_BASE}/settings/ai/test`, () => {
        testCalled = true;
        return HttpResponse.json({
          ok: true,
          message: "Connected. Model replied: ok",
          model_used: "test-model",
        });
      }),
    );

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    const testBtn = await screen.findByRole("button", {
      name: /test connection/i,
    });
    await user.click(testBtn);

    await waitFor(() => {
      expect(testCalled).toBe(true);
    });
    expect(
      await screen.findByText(/connected\. model replied/i),
    ).toBeInTheDocument();
  });
});
