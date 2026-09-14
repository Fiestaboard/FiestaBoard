import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiChatPanel } from "@/components/ai-chat-panel";
import type { UseAiChatResult } from "@/lib/use-ai-chat";

import enMessages from "../../messages/en.json";
import { server } from "./mocks/server";

const API_BASE = "/api";

// Mock the streaming hook so tests don't need a real SSE connection.
// Each test controls status / messages via `mockHook`.
const mockSend = vi.fn();
const mockApprove = vi.fn();
const mockAnswer = vi.fn();
const mockStop = vi.fn();
const mockReset = vi.fn();
const mockRetryLast = vi.fn();

// Typed against the real hook contract: without it the inferred literal
// types (`status: "idle"`, `messages: never[]`, `error: null`) reject the
// per-test overrides below.
const defaultHookResult: UseAiChatResult = {
  messages: [],
  status: "idle",
  pendingApproval: null,
  pendingElicitation: null,
  error: null,
  send: mockSend,
  approve: mockApprove,
  answer: mockAnswer,
  stop: mockStop,
  retryLast: mockRetryLast,
  reset: mockReset,
};

const CONFIGURED = {
  enabled: true,
  providers: [] as unknown[],
  default_provider_id: "p1",
};

const CREATE_PAGE_CALL = {
  id: "tc1",
  name: "create_page",
  args: { name: "Morning", template_lines: ["HELLO"] },
  title: "Create page",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp" as const,
};

let hookResult: UseAiChatResult = { ...defaultHookResult };

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

  it("Enter submits the message", async () => {
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
    await user.keyboard("{Enter}");

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

  it("stop button calls stop()", async () => {
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
    expect(mockStop).toHaveBeenCalledOnce();
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

  it("renders a tool call as a card that settles with its result", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
      ),
    );
    hookResult = {
      ...defaultHookResult,
      messages: [
        { role: "user", content: "make a page" },
        {
          role: "assistant",
          content: "Creating it.",
          toolCalls: [
            {
              ...CREATE_PAGE_CALL,
              phase: "ok",
              result: { id: "tc1", name: "create_page", status: "ok", summary: "Page created.", result: { page_id: "p9" }, error: null },
            },
          ],
        },
      ],
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const card = await screen.findByTestId("ai-tool-create_page");
    expect(card).toHaveAttribute("data-state", "output-available");
    expect(screen.getByRole("button", { name: /Create page.*Morning.*Done/ })).toBeInTheDocument();
  });

  it("shows the step timeline while the turn is running", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
      ),
    );
    hookResult = {
      ...defaultHookResult,
      status: "streaming",
      messages: [
        { role: "user", content: "make a page" },
        {
          role: "assistant",
          content: "",
          pending: true,
          statusMessage: "Running create_page…",
          toolCalls: [{ ...CREATE_PAGE_CALL, phase: "running" }],
        },
      ],
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const timeline = await screen.findByTestId("ai-step-timeline");
    expect(timeline).toHaveAttribute("role", "status");
    expect(timeline).toHaveTextContent("0 of 1 steps");
    expect(timeline).toHaveTextContent("Running create_page…");
  });

  it("shows Approve / Deny for the pending destructive call and forwards the decision", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
      ),
    );
    const pending = { ...CREATE_PAGE_CALL, id: "tc2", name: "delete_page", args: { page_id: "p1" }, destructive: true, requires_approval: true };
    hookResult = {
      ...defaultHookResult,
      status: "awaiting_approval",
      pendingApproval: pending,
      messages: [
        { role: "user", content: "delete it" },
        { role: "assistant", content: "Deleting.", toolCalls: [{ ...pending, phase: "awaiting_approval" }] },
      ],
    };

    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    expect(mockApprove).toHaveBeenCalledWith("tc2", "approve");
  });

  it("renders a question with chips and answers through the hook", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
      ),
    );
    const elicitation = {
      id: "q1",
      name: "ask_user",
      message: "Which board?",
      requested_schema: { type: "object" as const, properties: { answer: { type: "string" as const, enum: ["Kitchen", "Hall"] } } },
      allow_free_text: true,
    };
    hookResult = {
      ...defaultHookResult,
      status: "awaiting_input",
      pendingElicitation: elicitation,
      messages: [
        { role: "user", content: "put weather up" },
        { role: "assistant", content: "", elicitation },
      ],
    };

    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", { name: "Kitchen" }));
    expect(mockAnswer).toHaveBeenCalledWith("q1", { action: "accept", content: { answer: "Kitchen" } });
    expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", enMessages.aiChatPanel.placeholderAnswer);
  });

  it("empty-state suggestions and placeholders resolve through i18n", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
      ),
    );
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const chip = await screen.findByRole("button", { name: enMessages.aiChatPanel.suggestions.weather });
    expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", enMessages.aiChatPanel.placeholderEmpty);
    await user.click(chip);
    expect(mockSend).toHaveBeenCalledWith(enMessages.aiChatPanel.suggestions.weather);
  });

  it("header buttons resolve their aria-label through next-intl (no hardcoded English)", async () => {
    // Regression test for issue #1190: the close + clear-conversation
    // buttons must read their accessible name from the `aiChatPanel`
    // namespace in `web/messages/*.json`, not from a hardcoded literal
    // in JSX. We assert the rendered aria-label matches the en bundle
    // exactly — if anyone reverts to a literal that drifts from the
    // translation key, this test fails.
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

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    expect(
      await screen.findByRole("button", {
        name: enMessages.aiChatPanel.clearConversationAriaLabel,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: enMessages.aiChatPanel.closePanelAriaLabel,
      }),
    ).toBeInTheDocument();
  });
});
