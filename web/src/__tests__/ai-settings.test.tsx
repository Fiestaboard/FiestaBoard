import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiSettings } from "@/components/settings/ai-settings";

import { server } from "./mocks/server";

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
    expect(screen.getByText(/sent directly to the provider you configure/i)).toBeInTheDocument();
  });

  it("shows an empty state when no providers are configured", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    expect(await screen.findByText(/no providers configured yet/i)).toBeInTheDocument();
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

    // Provider rows are collapsed by default; click the row's summary
    // trigger to reveal the form fields.
    await user.click(await screen.findByText("Test"));

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
    const providers = (receivedBody as Record<string, unknown>)["providers"] as Array<{
      api_key: string;
      name: string;
    }>;
    expect(providers).toHaveLength(1);
    expect(providers[0].api_key).toBe("***");
    expect(providers[0].name).toBe("My OpenRouter");
  });

  it("can add a model to a provider via the model input", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Add an empty provider — it opens expanded so the form is visible.
    await screen.findByText(/no providers configured yet/i);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    const modelInput = screen.getByPlaceholderText("openai/gpt-4o-mini");
    await user.type(modelInput, "gpt-4o-mini");
    await user.keyboard("{Enter}");

    // The model badge appears; check via the remove-button label to avoid
    // ambiguous multi-element matches on the badge text node.
    expect(await screen.findByRole("button", { name: /remove model gpt-4o-mini/i })).toBeInTheDocument();
  });

  it("can remove a provider", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "My Provider",
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

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Provider row must be present before we click remove.
    expect(await screen.findByText("My Provider")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove provider/i }));

    // After removal the empty state message should appear.
    await waitFor(() => {
      expect(screen.getByText(/no providers configured yet/i)).toBeInTheDocument();
    });
  });

  it("api key field toggles between hidden and visible", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Open a new provider row (starts expanded).
    await screen.findByText(/no providers configured yet/i);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    // Use the exact label text to avoid matching the Show/Hide button's
    // aria-label which also contains "api key".
    const keyInput = await screen.findByLabelText("API Key");
    expect(keyInput).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: /show api key/i }));
    expect(keyInput).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: /hide api key/i }));
    expect(keyInput).toHaveAttribute("type", "password");
  });

  it("discard reverts draft changes", async () => {
    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Add a provider to create a draft.
    await screen.findByText(/no providers configured yet/i);
    await user.click(screen.getByRole("button", { name: /add provider/i }));

    // Save/Discard buttons should appear.
    expect(screen.getByRole("button", { name: /discard/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /discard/i }));

    // After discarding, the draft is cleared → empty state returns.
    await waitFor(() => {
      expect(screen.getByText(/no providers configured yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
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

    // Expand the collapsed provider row before clicking Test connection,
    // which lives inside the row's body.
    await user.click(await screen.findByText("Test"));

    const testBtn = await screen.findByRole("button", {
      name: /test connection/i,
    });
    await user.click(testBtn);

    await waitFor(() => {
      expect(testCalled).toBe(true);
    });
    expect(await screen.findByText(/connected\. model replied/i)).toBeInTheDocument();
  });

  it("test connection shows failure state when the server returns ok=false", async () => {
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
      http.post(`${API_BASE}/settings/ai/test`, () =>
        HttpResponse.json({
          ok: false,
          message: "Connection refused: provider unreachable",
          model_used: null,
        }),
      ),
    );

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    await user.click(await screen.findByText("Test"));

    const testBtn = await screen.findByRole("button", {
      name: /test connection/i,
    });
    await user.click(testBtn);

    expect(await screen.findByText(/connection refused: provider unreachable/i)).toBeInTheDocument();
  });

  it("make default button sets the default provider", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "Alpha",
              base_url: "https://alpha.test/v1",
              api_key: "***",
              models: ["m1"],
              default_model: "m1",
            },
            {
              id: "p2",
              name: "Beta",
              base_url: "https://beta.test/v1",
              api_key: "***",
              models: ["m2"],
              default_model: "m2",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();

    // Wait for both providers to appear.
    await screen.findByText("Alpha");
    await screen.findByText("Beta");

    // "Make default" button is visible for the non-default provider.
    const makeDefaultBtn = screen.getByRole("button", { name: /make default/i });
    await user.click(makeDefaultBtn);

    // Draft should now exist — Save/Discard appear.
    expect(await screen.findByRole("button", { name: /save changes/i })).toBeInTheDocument();
  });
});
