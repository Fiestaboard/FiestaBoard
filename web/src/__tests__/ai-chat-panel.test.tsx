import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiChatPanel } from "@/components/ai-chat-panel";

import { server } from "./mocks/server";

const API_BASE = "/api";

// Mock the streaming hook so tests don't need a real SSE connection.
// Each test controls status / messages via `mockHook`.
const mockSend = vi.fn();
const mockResume = vi.fn();
const mockCancel = vi.fn();
const mockReset = vi.fn();
const mockRetryLast = vi.fn();

const defaultHookResult = {
  messages: [],
  status: "idle" as const,
  error: null,
  send: mockSend,
  resume: mockResume,
  cancel: mockCancel,
  retryLast: mockRetryLast,
  reset: mockReset,
};

let hookResult = { ...defaultHookResult };

vi.mock("@/lib/use-ai-chat", () => ({
  useAiChat: () => hookResult,
}));

const CONFIGURED_PROVIDER = {
  id: "p1",
  name: "Test",
  base_url: "https://example.test/v1",
  api_key: "***",
  models: ["test-model"],
  default_model: "test-model",
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const noop = () => {};
const defaultProps = {
  getTurnContext: () => ({
    deviceType: "flagship" as const,
    surface: "global" as const,
    currentPage: undefined,
  }),
  onToolCall: noop,
  onClose: noop,
};

describe("AiChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hookResult = { ...defaultHookResult };
    // Default: no providers configured.
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: false,
          providers: [],
          default_provider_id: null,
        }),
      ),
    );
  });

  it("renders the FiestaBot (Beta) header", async () => {
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByText("FiestaBot (Beta)")).toBeInTheDocument();
  });

  it("shows close button that calls onClose", async () => {
    const onClose = vi.fn();
    render(<AiChatPanel {...defaultProps} onClose={onClose} />, {
      wrapper: Wrapper,
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /close fiestabot/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows AI-disabled warning when ai is disabled", async () => {
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByText(/ai is disabled/i)).toBeInTheDocument();
  });

  it("shows configure-provider warning when ai enabled but no providers", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [],
          default_provider_id: null,
        }),
      ),
    );
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByText(/configure an ai provider/i)).toBeInTheDocument();
  });

  it("textarea is disabled when no providers are configured", async () => {
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const textarea = await screen.findByRole("textbox");
    await waitFor(() => expect(textarea).toBeDisabled());
  });

  it("textarea is enabled when a provider is configured", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const textarea = await screen.findByRole("textbox");
    await waitFor(() => expect(textarea).not.toBeDisabled());
  });

  it("send button calls send() with the draft text", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    const textarea = await screen.findByRole("textbox");
    await waitFor(() => expect(textarea).not.toBeDisabled());

    await user.type(textarea, "Show me the weather");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(mockSend).toHaveBeenCalledWith("Show me the weather");
  });

  it("Ctrl+Enter submits the message", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    const textarea = await screen.findByRole("textbox");
    await waitFor(() => expect(textarea).not.toBeDisabled());

    await user.type(textarea, "Hello");
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(mockSend).toHaveBeenCalledWith("Hello");
  });

  it("shows Stop button and hides Send while streaming", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    hookResult = { ...defaultHookResult, status: "streaming" };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    expect(await screen.findByRole("button", { name: /stop/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
  });

  it("stop button calls cancel()", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    hookResult = { ...defaultHookResult, status: "streaming" };

    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: /stop/i }));
    expect(mockCancel).toHaveBeenCalledOnce();
  });

  it("clear conversation button is hidden with no messages", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await screen.findByText("FiestaBot (Beta)");
    expect(screen.queryByRole("button", { name: /clear conversation/i })).not.toBeInTheDocument();
  });

  it("clear conversation button is visible with messages and calls reset()", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    hookResult = {
      ...defaultHookResult,
      messages: [{ role: "user", content: "hi" }],
    };

    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: /clear conversation/i }));
    expect(mockReset).toHaveBeenCalledOnce();
  });

  it("shows error alert when status is error", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    hookResult = {
      ...defaultHookResult,
      status: "error",
      error: "Provider timeout after 30s",
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByText(/provider timeout after 30s/i)).toBeInTheDocument();
  });

  it("renders tool-result messages as compact pills, not user bubbles", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    hookResult = {
      ...defaultHookResult,
      messages: [
        {
          role: "user",
          content: '[Tool result: install_plugin for "openweather" → Success.]',
          isToolResult: true,
        },
      ],
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    // The pill strips the "[Tool result: " prefix when displaying
    expect(await screen.findByText(/install_plugin for "openweather" → Success/)).toBeInTheDocument();
  });

  it("shows ChainingModePicker when onChainingModeChange is provided", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    const onModeChange = vi.fn();
    render(<AiChatPanel {...defaultProps} chainingMode="manual" onChainingModeChange={onModeChange} />, {
      wrapper: Wrapper,
    });
    // ChainingModePicker renders a button with the mode name
    expect(await screen.findByTitle(/ai mode: manual/i)).toBeInTheDocument();
  });

  it("does not show ChainingModePicker when onChainingModeChange is absent", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [CONFIGURED_PROVIDER],
          default_provider_id: "p1",
        }),
      ),
    );
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await screen.findByText("FiestaBot (Beta)");
    expect(screen.queryByTitle(/ai mode:/i)).not.toBeInTheDocument();
  });
});
