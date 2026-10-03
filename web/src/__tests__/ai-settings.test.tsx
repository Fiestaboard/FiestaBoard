import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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

    // Collected rather than held in a `let`: TypeScript cannot see the
    // closure assignment and would narrow a nullable local back to `null`.
    const receivedBodies: Record<string, unknown>[] = [];
    server.use(
      http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        receivedBodies.push(body);
        return HttpResponse.json(body);
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
      expect(receivedBodies).toHaveLength(1);
    });
    // The masked api_key MUST be sent back as-is so the backend
    // preserves the stored secret.
    const providers = receivedBodies[0]["providers"] as Array<{
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

  it("Save never sends approval_mode: the page has no control for it and must not revert the chat pill", async () => {
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
          approval_mode: "auto",
        }),
      ),
    );
    const receivedBodies: Record<string, unknown>[] = [];
    server.use(
      http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        receivedBodies.push(body);
        return HttpResponse.json({ ...body, approval_mode: "auto" });
      }),
    );

    render(<AiSettings />, { wrapper: Wrapper });
    const user = userEvent.setup();
    await user.click(await screen.findByText("Test"));
    const nameInput = await screen.findByLabelText(/^Name$/);
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(receivedBodies).toHaveLength(1));
    expect(receivedBodies[0]).not.toHaveProperty("approval_mode");
    expect(receivedBodies[0]).toHaveProperty("providers");
  });

  // -- Per-turn caps --

  describe("turn limits", () => {
    /** The stored block, with whatever caps the install has set. */
    function withCaps(caps: { max_model_calls: number | null; max_tool_calls: number | null }) {
      server.use(
        http.get(`${API_BASE}/settings/ai`, () =>
          HttpResponse.json({
            enabled: true,
            providers: [],
            default_provider_id: null,
            approval_mode: "ask",
            ...caps,
          }),
        ),
      );
    }

    it("leaves the fields blank when the install has no override", async () => {
      withCaps({ max_model_calls: null, max_tool_calls: null });
      render(<AiSettings />, { wrapper: Wrapper });

      const field = await screen.findByLabelText(/Model calls per turn/i);
      // Blank, with the placeholder saying where the number comes from — not
      // a number this page invented and would have to keep in sync.
      expect(field).toHaveValue(null);
      expect(field).toHaveAttribute("placeholder", "Server default");
    });

    it("shows the stored caps", async () => {
      withCaps({ max_model_calls: 40, max_tool_calls: 90 });
      render(<AiSettings />, { wrapper: Wrapper });

      expect(await screen.findByLabelText(/Model calls per turn/i)).toHaveValue(40);
      expect(screen.getByLabelText(/Tool calls per turn/i)).toHaveValue(90);
    });

    it("saves an edited cap", async () => {
      withCaps({ max_model_calls: null, max_tool_calls: null });
      const receivedBodies: Record<string, unknown>[] = [];
      server.use(
        http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
          const body = (await request.json()) as Record<string, unknown>;
          receivedBodies.push(body);
          return HttpResponse.json({ enabled: true, providers: [], default_provider_id: null, ...body });
        }),
      );
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();

      const field = await screen.findByLabelText(/Model calls per turn/i);
      await user.type(field, "40");
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(receivedBodies).toHaveLength(1));
      expect(receivedBodies[0].max_model_calls).toBe(40);
    });

    it("clearing a cap sends null, handing the turn back to the server defaults", async () => {
      withCaps({ max_model_calls: 40, max_tool_calls: null });
      const receivedBodies: Record<string, unknown>[] = [];
      server.use(
        http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
          const body = (await request.json()) as Record<string, unknown>;
          receivedBodies.push(body);
          return HttpResponse.json({ enabled: true, providers: [], default_provider_id: null, ...body });
        }),
      );
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();

      const field = await screen.findByLabelText(/Model calls per turn/i);
      await user.clear(field);
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(receivedBodies).toHaveLength(1));
      // Explicitly null, not absent: the config manager clears the override
      // on a null and ignores a missing key.
      expect(receivedBodies[0].max_model_calls).toBeNull();
    });
  });

  describe("signing in instead of pasting an API key", () => {
    const SAVED = {
      id: "p1",
      name: "Test",
      base_url: "https://example.test/v1",
      api_key: "***",
      models: ["test-model"],
      default_model: "test-model",
    };

    function serveSettings(...providers: Record<string, unknown>[]) {
      server.use(
        http.get(`${API_BASE}/settings/ai`, () =>
          HttpResponse.json({ enabled: true, providers, default_provider_id: "p1" }),
        ),
      );
    }

    function captureSaves(): Record<string, unknown>[] {
      const bodies: Record<string, unknown>[] = [];
      server.use(
        http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
          const body = (await request.json()) as Record<string, unknown>;
          bodies.push(body);
          return HttpResponse.json(body);
        }),
      );
      return bodies;
    }

    it("offers OpenRouter, Hugging Face and ChatGPT sign-in beside the API key field, which stays", async () => {
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await screen.findByText(/no providers configured yet/i);
      await user.click(screen.getByRole("button", { name: /add provider/i }));

      expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
      const choices = screen.getByRole("group", { name: "Or sign in instead of using an API key" });
      expect(within(choices).getByRole("button", { name: "Sign in with OpenRouter" })).toBeInTheDocument();
      expect(within(choices).getByRole("button", { name: "Sign in with Hugging Face" })).toBeInTheDocument();
      expect(within(choices).getByRole("button", { name: "Sign in with ChatGPT" })).toBeInTheDocument();
    });

    it("choosing a sign-in saves its preset and the matching endpoint, and leaves the API key alone", async () => {
      serveSettings(SAVED);
      const bodies = captureSaves();
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Sign in with Hugging Face" }));
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(bodies).toHaveLength(1));
      const [provider] = bodies[0].providers as Array<Record<string, unknown>>;
      expect(provider.sign_in).toEqual({ preset: "huggingface" });
      expect(provider.base_url).toBe("https://router.huggingface.co/v1");
      expect(provider.protocol).toBe("openai");
      expect(provider.api_key).toBe("***");
      expect(provider.name).toBe("Test");
    });

    it("ChatGPT sign-in uses the Responses protocol", async () => {
      serveSettings(SAVED);
      const bodies = captureSaves();
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Sign in with ChatGPT" }));
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(bodies).toHaveLength(1));
      const [provider] = bodies[0].providers as Array<Record<string, unknown>>;
      expect(provider.sign_in).toEqual({ preset: "openai_chatgpt" });
      expect(provider.base_url).toBe("https://api.openai.com/v1");
      expect(provider.protocol).toBe("openai_responses");
    });

    it("asks to save before signing in, since the board only knows saved providers", async () => {
      serveSettings(SAVED);
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Sign in with OpenRouter" }));
      expect(screen.getByText("Save changes, then sign in to OpenRouter here.")).toBeInTheDocument();
      expect(screen.queryByTestId("oauth-connection")).not.toBeInTheDocument();
    });

    it("shows the account connection of a saved signed-in provider", async () => {
      serveSettings({ ...SAVED, sign_in: { preset: "openrouter" } });
      server.use(
        http.get(`${API_BASE}/oauth/connections`, () =>
          HttpResponse.json({
            redirect_uri: "https://fiestaboard.app/auth/oauth/redirect",
            connections: [
              {
                id: "ai.p1",
                kind: "ai",
                plugin_id: "ai",
                instance_label: null,
                plugin_name: "Test (FiestaBot)",
                provider_name: "OpenRouter",
                flows: ["key_exchange"],
                configured: true,
                user_app: false,
                shared_app: false,
                client_id_setting: null,
                client_secret_setting: null,
                app_setup_url: "",
                status: "reauthorization_required",
                status_reason: "rejected",
                scopes: [],
                expires_at: null,
                connected_at: null,
                device: null,
              },
            ],
          }),
        ),
      );
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));

      const panel = await screen.findByTestId("oauth-connection");
      expect(within(panel).getByText("Reconnect needed")).toBeInTheDocument();
      expect(within(panel).getByText("OpenRouter stopped accepting the sign-in. Sign in again.")).toBeInTheDocument();
      // The key field stays, and says it is not used while sign-in is on.
      expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
      expect(screen.getByText(/not used while you sign in/)).toBeInTheDocument();
    });

    it("can go back to the API key, which drops the sign-in on save", async () => {
      serveSettings({ ...SAVED, sign_in: { preset: "openrouter" } });
      const bodies = captureSaves();
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Use the API key instead" }));
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(bodies).toHaveLength(1));
      const [provider] = bodies[0].providers as Array<Record<string, unknown>>;
      expect(provider).not.toHaveProperty("sign_in");
      expect(provider.api_key).toBe("***");
    });

    it("an API-key provider saves exactly as before, with no sign_in", async () => {
      serveSettings(SAVED);
      const bodies = captureSaves();
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      const name = screen.getByLabelText(/^Name$/);
      await user.clear(name);
      await user.type(name, "Renamed");
      await user.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => expect(bodies).toHaveLength(1));
      const [provider] = bodies[0].providers as Array<Record<string, unknown>>;
      expect(provider).toEqual({ ...SAVED, name: "Renamed" });
    });
  });

  describe("picking a model from the provider", () => {
    const SAVED = {
      id: "p1",
      name: "Test",
      base_url: "https://example.test/v1",
      api_key: "***",
      models: ["test-model"],
      default_model: "test-model",
    };

    function serveSettings() {
      server.use(
        http.get(`${API_BASE}/settings/ai`, () =>
          HttpResponse.json({ enabled: true, providers: [SAVED], default_provider_id: "p1" }),
        ),
      );
    }

    it("loads the saved provider's models and adds the one picked", async () => {
      serveSettings();
      let asked = "";
      server.use(
        http.get(`${API_BASE}/settings/ai/providers/:id/models`, ({ params }) => {
          asked = String(params.id);
          return HttpResponse.json({
            models: [
              { id: "test-model", name: "Test Model" },
              { id: "test-other", name: "Test Other" },
            ],
          });
        }),
      );
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Load models" }));

      const picker = await screen.findByRole("combobox", { name: "Add a model from the provider" });
      expect(asked).toBe("p1");
      await user.click(picker);
      // A model already in the list is not offered again.
      expect(screen.queryByRole("option", { name: /Test Model/ })).not.toBeInTheDocument();
      await user.click(await screen.findByRole("option", { name: /Test Other/ }));

      expect(await screen.findByRole("button", { name: "Remove model test-other" })).toBeInTheDocument();
      // Typing a model by hand still works beside the picker.
      expect(screen.getByPlaceholderText("openai/gpt-4o-mini")).toBeInTheDocument();
    });

    it("says why when the provider cannot list its models", async () => {
      serveSettings();
      server.use(
        http.get(`${API_BASE}/settings/ai/providers/:id/models`, () =>
          HttpResponse.json({ detail: "AI provider returned 401 when asked for its models." }, { status: 502 }),
        ),
      );
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await user.click(await screen.findByText("Test"));
      await user.click(screen.getByRole("button", { name: "Load models" }));

      expect(await screen.findByText(/returned 401 when asked for its models/)).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: "Add a model from the provider" })).not.toBeInTheDocument();
    });

    it("offers no model list for a provider that is not saved yet", async () => {
      render(<AiSettings />, { wrapper: Wrapper });
      const user = userEvent.setup();
      await screen.findByText(/no providers configured yet/i);
      await user.click(screen.getByRole("button", { name: /add provider/i }));

      expect(screen.queryByRole("button", { name: "Load models" })).not.toBeInTheDocument();
    });
  });
});
