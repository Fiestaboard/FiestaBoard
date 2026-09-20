import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiChatPanel } from "@/components/ai-chat-panel";
import type { UseAiChatOptions, UseAiChatResult } from "@/lib/use-ai-chat";

import enMessages from "../../messages/en.json";
import { server } from "./mocks/server";

const API_BASE = "/api";

// Mock the streaming hook so tests don't need a real SSE connection.
// Each test controls status / messages via `mockHook`.
const mockSend = vi.fn();
const mockApprove = vi.fn();
const mockAnswer = vi.fn();
const mockStop = vi.fn();
const mockRetryLast = vi.fn();
const mockDisableAutoApprove = vi.fn();
const mockNewConversation = vi.fn();
const mockLoadConversation = vi.fn();
const mockForgetConversation = vi.fn();

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
  autoApprove: false,
  disableAutoApprove: mockDisableAutoApprove,
  conversationId: null,
  newConversation: mockNewConversation,
  loadConversation: mockLoadConversation,
  forgetConversation: mockForgetConversation,
};

const CONFIGURED = {
  enabled: true,
  providers: [] as unknown[],
  default_provider_id: "p1",
  approval_mode: "ask",
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
// The options the panel hands the hook, so a test can fire its callbacks.
let capturedHookOpts: UseAiChatOptions | null = null;

vi.mock("@/lib/use-ai-chat", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/use-ai-chat")>()),
  useAiChat: (opts: UseAiChatOptions) => {
    capturedHookOpts = opts;
    return hookResult;
  },
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

/**
 * The panel decides its own layout from its measured width (the composer
 * hint, in particular), and jsdom measures everything as zero. Give it a
 * width for the duration of one test.
 */
function withPanelWidth(width: number) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    width,
    height: 600,
    top: 0,
    left: 0,
    right: width,
    bottom: 600,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

/** Wide enough for the composer to keep the keyboard hint in the toolbar. */
const ROOMY = 600;

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
    capturedHookOpts = null;
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

  it("names itself FiestaBot, with no Beta anywhere in the header", async () => {
    const { container } = render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByText("FiestaBot")).toBeInTheDocument();

    // It shipped as "FiestaBot (Beta)" and then as a name plus a Beta badge;
    // it is out of beta now. This fails whichever way Beta comes back — in
    // the title string, or as a badge beside it.
    const header = container.querySelector('[data-slot="card"] > div');
    expect(header).not.toBeNull();
    expect(header!.textContent).toContain("FiestaBot");
    expect(header!.textContent).not.toMatch(/beta/i);
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

  // Issue #2020: the composer used to render a lone `Enter` code glyph among
  // the provider/model pickers. The hint now lives beside the Send button,
  // with a verb, as keycaps — and the shortcut reaches assistive tech
  // through the button itself rather than through the decorative hint.
  describe("send hint", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/settings/ai`, () =>
          HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] }),
        ),
      );
    });

    it("no longer renders a bare Enter glyph among the toolbar tools", async () => {
      const { container } = render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      const tools = container.querySelector('[data-slot="prompt-input-tools"]');
      expect(tools).not.toBeNull();
      expect(tools).not.toHaveTextContent(/Enter/);
    });

    it("renders Enter to send and Shift+Enter for a new line as keycaps beside Send", async () => {
      withPanelWidth(ROOMY);
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      const hint = screen.getByTestId("ai-chat-send-hint");
      const caps = Array.from(hint.querySelectorAll('kbd[data-slot="kbd-key"]')).map((el) => el.textContent);
      expect(caps).toEqual(["Enter", "Shift", "Enter"]);
      expect(hint).toHaveTextContent(enMessages.aiChatPanel.enterToSend);
      expect(hint).toHaveTextContent(enMessages.aiChatPanel.shiftEnterNewline);
      // Beside the Send button, not among the model pickers.
      expect(hint.parentElement).toContainElement(screen.getByRole("button", { name: /send/i }));
    });

    it("keeps the hint decorative: hidden from assistive tech and on coarse pointers", async () => {
      withPanelWidth(ROOMY);
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      const hint = screen.getByTestId("ai-chat-send-hint");
      expect(hint).toHaveAttribute("aria-hidden", "true");
      // Touch keyboards have no Shift+Enter; the hint would only mislead.
      expect(hint).toHaveClass("pointer-coarse:hidden");
    });

    it("gives the hint up at drawer width and puts it on the Send button instead", async () => {
      withPanelWidth(384);
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      // 384px is the drawer's default width, where #2024 had the hint
      // painted over the provider and model pickers.
      expect(screen.queryByTestId("ai-chat-send-hint")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /send/i })).toHaveAttribute(
        "title",
        enMessages.aiChatPanel.sendShortcut,
      );
    });

    it("keeps the hint once the panel is wide enough to hold it", async () => {
      withPanelWidth(ROOMY);
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      expect(screen.getByTestId("ai-chat-send-hint")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /send/i })).not.toHaveAttribute("title");
    });

    it("lets every control in the composer row shrink except Send", async () => {
      withPanelWidth(384);
      const { container } = render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      // The collision in #2024 was structural: a `shrink-0` hint beside a
      // `flex-wrap` tools group. Nothing in the row may refuse to shrink
      // apart from the button that sends.
      const tools = container.querySelector('[data-slot="prompt-input-tools"]');
      expect(tools).toHaveClass("min-w-0", "flex-1", "flex-nowrap", "overflow-hidden");
      expect(tools).not.toHaveClass("flex-wrap");
      expect(screen.getByRole("button", { name: /send/i })).toHaveClass("shrink-0");
    });

    it("advertises Enter on the send button through aria-keyshortcuts", async () => {
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      await screen.findByRole("textbox");

      expect(screen.getByRole("button", { name: /send/i })).toHaveAttribute("aria-keyshortcuts", "Enter");
    });

    it("Shift+Enter inserts a newline instead of sending (what the hint promises)", async () => {
      const user = userEvent.setup();
      render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
      const textarea = await screen.findByRole("textbox");
      await waitFor(() => expect(textarea).not.toBeDisabled());

      await user.type(textarea, "Hello");
      await user.keyboard("{Shift>}{Enter}{/Shift}");

      expect(mockSend).not.toHaveBeenCalled();
      expect(textarea).toHaveValue("Hello\n");
    });
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

  it("the New chat button is disabled with no messages", async () => {
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
    await screen.findByText("FiestaBot");
    expect(screen.getByRole("button", { name: enMessages.aiChatPanel.newChatAriaLabel })).toBeDisabled();
  });

  it("New chat with messages calls newConversation()", async () => {
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

    await user.click(await screen.findByRole("button", { name: enMessages.aiChatPanel.newChatAriaLabel }));
    expect(mockNewConversation).toHaveBeenCalledOnce();
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
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
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
              result: {
                id: "tc1",
                name: "create_page",
                status: "ok",
                summary: "Page created.",
                result: { page_id: "p9" },
                error: null,
              },
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
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
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
          status: { phase: "tool_running", toolCallId: "tc1" },
          toolCalls: [{ ...CREATE_PAGE_CALL, phase: "running" }],
        },
      ],
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const timeline = await screen.findByTestId("ai-step-timeline");
    expect(timeline).toHaveAttribute("role", "status");
    expect(timeline).toHaveTextContent("0 of 1 steps");
    // The status line is built from the frame's phase and the tool's
    // translated label, never from the server's English `message`.
    expect(timeline).toHaveTextContent("Running Create page…");
    expect(timeline).not.toHaveTextContent("create_page");
  });

  it("consecutive assistant entries render as one turn, with steps from all of them", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
    );
    hookResult = {
      ...defaultHookResult,
      status: "streaming",
      messages: [
        { role: "user", content: "delete it" },
        {
          role: "assistant",
          content: "Deleting.",
          toolCalls: [{ ...CREATE_PAGE_CALL, id: "tc2", name: "delete_page", args: { page_id: "p1" }, phase: "ok" }],
        },
        { role: "assistant", content: "Gone.", pending: true, status: { phase: "thinking", toolCallId: null } },
      ],
    };

    const { container } = render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const assistantTurns = container.querySelectorAll('[data-slot="message"][data-from="assistant"]');
    expect(assistantTurns).toHaveLength(1);
    expect(assistantTurns[0]).toHaveTextContent("Deleting.");
    expect(assistantTurns[0]).toHaveTextContent("Gone.");
    const timeline = await screen.findByTestId("ai-step-timeline");
    expect(timeline).toHaveTextContent("1 of 1 steps");
    expect(timeline).toHaveTextContent(enMessages.aiChatPanel.status.thinking);
  });

  it("collapses a run of the same successful action into one row that opens to the cards", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
    );
    const schedule = (id: string, start: string) => ({
      ...CREATE_PAGE_CALL,
      id,
      name: "create_schedule",
      args: { page_id: "p1", start_time: start, end_time: "09:00", day_pattern: "all" },
      phase: "ok" as const,
    });
    hookResult = {
      ...defaultHookResult,
      messages: [
        { role: "user", content: "set up my day" },
        {
          role: "assistant",
          content: "Done.",
          toolCalls: [
            schedule("s1", "07:00"),
            schedule("s2", "09:00"),
            schedule("s3", "17:00"),
            schedule("s4", "21:00"),
          ],
        },
      ],
    };

    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });

    // Four two-line cards became one row that says how many there were.
    const run = await screen.findByTestId("ai-tool-run-create_schedule");
    expect(run).toHaveTextContent("4");
    expect(screen.queryAllByTestId("ai-tool-create_schedule")).toHaveLength(0);

    // And the cards are still there, a click away — nothing is hidden.
    await user.click(within(run).getAllByRole("button")[0]);
    expect(screen.getAllByTestId("ai-tool-create_schedule")).toHaveLength(4);
  });

  it("leaves a call that needed approval as its own card, never inside a run", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
    );
    const deletion = (id: string) => ({
      ...CREATE_PAGE_CALL,
      id,
      name: "delete_schedule",
      args: { schedule_id: id },
      destructive: true,
      requires_approval: true,
      phase: "ok" as const,
    });
    hookResult = {
      ...defaultHookResult,
      messages: [
        { role: "user", content: "delete those two" },
        { role: "assistant", content: "Done.", toolCalls: [deletion("d1"), deletion("d2")] },
      ],
    };

    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findAllByTestId("ai-tool-delete_schedule")).toHaveLength(2);
    expect(screen.queryByTestId("ai-tool-run-delete_schedule")).not.toBeInTheDocument();
  });

  it("shows Approve / Deny for the pending destructive call and forwards the decision", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
    );
    const pending = {
      ...CREATE_PAGE_CALL,
      id: "tc2",
      name: "delete_page",
      args: { page_id: "p1" },
      destructive: true,
      requires_approval: true,
    };
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
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
    );
    const elicitation = {
      id: "q1",
      name: "ask_user",
      message: "Which board?",
      requested_schema: {
        type: "object" as const,
        properties: { answer: { type: "string" as const, enum: ["Kitchen", "Hall"] } },
      },
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
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
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
        name: enMessages.aiChatPanel.newChatAriaLabel,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: enMessages.aiChatPanel.historyAriaLabel,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: enMessages.aiChatPanel.closePanelAriaLabel,
      }),
    ).toBeInTheDocument();
  });

  // -- Conversation history (#2022) --

  const CONV_A = "11111111-1111-4111-8111-111111111111";
  const CONV_B = "22222222-2222-4222-8222-222222222222";
  const SUMMARIES = [
    {
      id: CONV_A,
      title: "Weather for the commute",
      created_at: "2026-09-19T10:00:00+00:00",
      updated_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      message_count: 3,
      provider_id: "p1",
      model: "test-model",
    },
    {
      id: CONV_B,
      title: "Stock ticker",
      created_at: "2026-09-10T10:00:00+00:00",
      updated_at: new Date(Date.now() - 3 * 24 * 3600_000).toISOString(),
      message_count: 1,
      provider_id: "p1",
      model: "test-model",
    },
  ];
  const CONV_A_FULL = {
    ...SUMMARIES[0],
    approval: false,
    messages: [
      { role: "user", content: "Weather for the commute" },
      { role: "assistant", content: "Here is your commute page." },
    ],
  };

  function withHistory(summaries = SUMMARIES) {
    let current = [...summaries];
    const deletes: string[] = [];
    const patches: Array<{ id: string; title: string }> = [];
    let cleared = 0;
    server.use(
      http.get(`${API_BASE}/settings/ai`, () => HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] })),
      http.get(`${API_BASE}/ai/conversations`, ({ request }) => {
        const q = (new URL(request.url).searchParams.get("q") ?? "").toLowerCase();
        const rows = q ? current.filter((c) => c.title.toLowerCase().includes(q)) : current;
        return HttpResponse.json({ conversations: rows, total: rows.length });
      }),
      http.get(`${API_BASE}/ai/conversations/${CONV_A}`, () => HttpResponse.json(CONV_A_FULL)),
      http.patch(`${API_BASE}/ai/conversations/:id`, async ({ params, request }) => {
        const body = (await request.json()) as { title: string };
        patches.push({ id: String(params.id), title: body.title });
        current = current.map((c) => (c.id === params.id ? { ...c, title: body.title } : c));
        return HttpResponse.json({ ...CONV_A_FULL, id: params.id, title: body.title });
      }),
      http.delete(`${API_BASE}/ai/conversations/:id`, ({ params }) => {
        deletes.push(String(params.id));
        current = current.filter((c) => c.id !== params.id);
        return HttpResponse.json({ id: params.id });
      }),
      http.delete(`${API_BASE}/ai/conversations`, () => {
        cleared += current.length;
        current = [];
        return HttpResponse.json({ deleted: cleared });
      }),
    );
    return {
      deletes,
      patches,
      cleared: () => cleared,
      add: (row: (typeof SUMMARIES)[number]) => {
        current = [row, ...current];
      },
    };
  }

  async function openHistory() {
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", { name: enMessages.aiChatPanel.historyAriaLabel }));
    return user;
  }

  it("History lists the saved conversations newest first with a relative time and message count", async () => {
    withHistory();
    await openHistory();

    const rows = await screen.findAllByRole("button", { name: /^open /i });
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("Weather for the commute"),
      expect.stringContaining("Stock ticker"),
    ]);
    expect(rows[0].textContent).toMatch(/5 minutes ago/);
    expect(rows[0].textContent).toMatch(/3 messages/);
    expect(rows[1].textContent).toMatch(/3 days ago/);
    expect(rows[1].textContent).toMatch(/1 message\b/);
  });

  it("History shows an empty state when nothing is saved", async () => {
    withHistory([]);
    await openHistory();
    expect(await screen.findByText(enMessages.aiChatPanel.history.empty)).toBeInTheDocument();
  });

  it("the search box filters the list by title", async () => {
    withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open weather for the commute/i });
    await user.type(screen.getByRole("searchbox", { name: enMessages.aiChatPanel.history.searchAriaLabel }), "stock");
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /open weather for the commute/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /open stock ticker/i })).toBeInTheDocument();
  });

  it("opening a saved conversation shows it read-only, and Continue makes it the live chat", async () => {
    withHistory();
    mockLoadConversation.mockResolvedValue(CONV_A_FULL);
    const user = await openHistory();

    await user.click(await screen.findByRole("button", { name: /open weather for the commute/i }));
    expect(await screen.findByText("Here is your commute page.")).toBeInTheDocument();
    expect(screen.getByText(enMessages.aiChatPanel.history.readOnly)).toBeInTheDocument();
    // Read-only: no composer while reviewing.
    expect(screen.queryByLabelText(enMessages.aiChatPanel.messageLabel)).not.toBeInTheDocument();
    const exportLink = screen.getByRole("link", { name: enMessages.aiChatPanel.history.export });
    expect(exportLink).toHaveAttribute("href", `/api/ai/conversations/${CONV_A}/export`);

    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.history.continue }));
    expect(mockLoadConversation).toHaveBeenCalledWith(CONV_A);
    // Back in the live chat: the composer is up and the review banner is gone.
    expect(await screen.findByLabelText(enMessages.aiChatPanel.messageLabel)).toBeInTheDocument();
    expect(screen.queryByText(enMessages.aiChatPanel.history.readOnly)).not.toBeInTheDocument();
  });

  it("delete removes the conversation from the list", async () => {
    const { deletes } = withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });

    await user.click(screen.getByRole("button", { name: /delete stock ticker/i }));

    await waitFor(() => expect(deletes).toEqual([CONV_B]));
    await waitFor(() => expect(screen.queryByRole("button", { name: /open stock ticker/i })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /open weather for the commute/i })).toBeInTheDocument();
  });

  it("rename saves the new title through PATCH", async () => {
    const { patches } = withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });

    await user.click(screen.getByRole("button", { name: /rename stock ticker/i }));
    const field = screen.getByRole("textbox", { name: enMessages.aiChatPanel.history.renameLabel });
    await user.clear(field);
    await user.type(field, "Ticker board{Enter}");

    await waitFor(() => expect(patches).toEqual([{ id: CONV_B, title: "Ticker board" }]));
    expect(await screen.findByRole("button", { name: /open ticker board/i })).toBeInTheDocument();
  });

  it("Clear all asks for confirmation, then empties the list", async () => {
    const h = withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });

    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.history.clearAll }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(enMessages.aiChatPanel.history.clearAllTitle);
    expect(h.cleared()).toBe(0);

    await user.click(within(dialog).getByRole("button", { name: enMessages.aiChatPanel.history.clearAllConfirm }));

    await waitFor(() => expect(h.cleared()).toBe(2));
    expect(await screen.findByText(enMessages.aiChatPanel.history.empty)).toBeInTheDocument();
  });

  it("deleting the live conversation tells the hook to forget its id", async () => {
    withHistory();
    hookResult = { ...defaultHookResult, conversationId: CONV_B, messages: [{ role: "user", content: "hi" }] };
    const user = await openHistory();
    await user.click(await screen.findByRole("button", { name: /delete stock ticker/i }));
    await waitFor(() => expect(mockForgetConversation).toHaveBeenCalledOnce());
  });

  it("deleting another conversation leaves the live id alone", async () => {
    const { deletes } = withHistory();
    hookResult = { ...defaultHookResult, conversationId: CONV_A, messages: [{ role: "user", content: "hi" }] };
    const user = await openHistory();
    await user.click(await screen.findByRole("button", { name: /delete stock ticker/i }));
    await waitFor(() => expect(deletes).toEqual([CONV_B]));
    expect(mockForgetConversation).not.toHaveBeenCalled();
  });

  it("Clear all forgets the live id too", async () => {
    const h = withHistory();
    hookResult = { ...defaultHookResult, conversationId: CONV_A, messages: [{ role: "user", content: "hi" }] };
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });
    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.history.clearAll }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: enMessages.aiChatPanel.history.clearAllConfirm }));
    await waitFor(() => expect(h.cleared()).toBe(2));
    await waitFor(() => expect(mockForgetConversation).toHaveBeenCalledOnce());
  });

  it("a successful autosave refreshes History even inside the query staleTime", async () => {
    const h = withHistory([SUMMARIES[1]]);
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
    render(
      <QueryClientProvider client={qc}>
        <AiChatPanel {...defaultProps} />
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole("button", { name: enMessages.aiChatPanel.historyAriaLabel }));
    await screen.findByRole("button", { name: /open stock ticker/i });
    expect(screen.queryByRole("button", { name: /open weather for the commute/i })).not.toBeInTheDocument();

    // The server gains a row; the hook reports a save landed.
    h.add(SUMMARIES[0]);
    expect(capturedHookOpts?.onSaved).toBeTypeOf("function");
    act(() => {
      capturedHookOpts?.onSaved?.(CONV_A);
    });
    expect(await screen.findByRole("button", { name: /open weather for the commute/i })).toBeInTheDocument();
  });

  it("Escape in the rename field cancels the rename without reaching the drawer", async () => {
    withHistory();
    const onWindowKey = vi.fn();
    window.addEventListener("keydown", onWindowKey);
    try {
      const user = await openHistory();
      await screen.findByRole("button", { name: /open stock ticker/i });
      await user.click(screen.getByRole("button", { name: /rename stock ticker/i }));
      const field = screen.getByRole("textbox", { name: enMessages.aiChatPanel.history.renameLabel });
      await user.type(field, "x{Escape}");
      expect(
        screen.queryByRole("textbox", { name: enMessages.aiChatPanel.history.renameLabel }),
      ).not.toBeInTheDocument();
      const keys = onWindowKey.mock.calls.map(([event]) => (event as KeyboardEvent).key);
      expect(keys).toContain("x"); // the listener works …
      expect(keys).not.toContain("Escape"); // … and Escape stayed in the field
    } finally {
      window.removeEventListener("keydown", onWindowKey);
    }
  });

  it("a cancelled rename does not leak its text into the next rename", async () => {
    withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });
    await user.click(screen.getByRole("button", { name: /rename stock ticker/i }));
    const field = screen.getByRole("textbox", { name: enMessages.aiChatPanel.history.renameLabel });
    await user.clear(field);
    await user.type(field, "junk");
    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.history.cancel }));

    await user.click(screen.getByRole("button", { name: /rename stock ticker/i }));
    expect(screen.getByRole("textbox", { name: enMessages.aiChatPanel.history.renameLabel })).toHaveValue(
      "Stock ticker",
    );
  });

  it("Back from History moves focus to the composer", async () => {
    withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });
    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.backAriaLabel }));
    const composer = await screen.findByLabelText(enMessages.aiChatPanel.messageLabel);
    await waitFor(() => expect(composer).toHaveFocus());
  });

  it("Back from a review moves focus to the History search", async () => {
    withHistory();
    const user = await openHistory();
    await user.click(await screen.findByRole("button", { name: /open weather for the commute/i }));
    await screen.findByText("Here is your commute page.");
    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.backAriaLabel }));
    const search = await screen.findByRole("searchbox", { name: enMessages.aiChatPanel.history.searchAriaLabel });
    await waitFor(() => expect(search).toHaveFocus());
  });

  it("History is unavailable while a turn is paused on approval", async () => {
    configuredWith("ask");
    hookResult = {
      ...defaultHookResult,
      status: "awaiting_approval",
      pendingApproval: {
        ...CREATE_PAGE_CALL,
        id: "tc2",
        name: "delete_page",
        destructive: true,
        requires_approval: true,
      },
      messages: [{ role: "user", content: "delete it" }],
    };
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByRole("button", { name: enMessages.aiChatPanel.historyAriaLabel })).toBeDisabled();
  });

  it("the streaming spinner stays visible in History", async () => {
    withHistory();
    hookResult = { ...defaultHookResult, messages: [{ role: "user", content: "hi" }] };
    const user = userEvent.setup();
    const { rerender } = render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await user.click(await screen.findByRole("button", { name: enMessages.aiChatPanel.historyAriaLabel }));
    await screen.findByRole("button", { name: /open stock ticker/i });
    expect(screen.queryByTestId("ai-chat-streaming")).not.toBeInTheDocument();

    hookResult = { ...hookResult, status: "streaming" };
    rerender(<AiChatPanel {...defaultProps} />);
    expect(await screen.findByTestId("ai-chat-streaming")).toBeInTheDocument();
  });

  it("Back returns from History to the live chat", async () => {
    withHistory();
    const user = await openHistory();
    await screen.findByRole("button", { name: /open stock ticker/i });
    await user.click(screen.getByRole("button", { name: enMessages.aiChatPanel.backAriaLabel }));
    expect(await screen.findByLabelText(enMessages.aiChatPanel.messageLabel)).toBeInTheDocument();
  });

  // -- Approval modes (#2021) --

  function configuredWith(approval_mode: "ask" | "auto") {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER], approval_mode }),
      ),
    );
  }

  it("the header mode toggle reads the install's approval_mode", async () => {
    configuredWith("auto");
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const group = await screen.findByRole("radiogroup", { name: enMessages.aiChatPanel.approvalMode.label });
    expect(group).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto })).toBeChecked(),
    );
    expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask })).not.toBeChecked();
  });

  it("choosing Auto writes approval_mode through PUT /settings/ai and shows the one-line note", async () => {
    configuredWith("ask");
    const puts: unknown[] = [];
    server.use(
      http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        puts.push(body);
        return HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER], ...body });
      }),
    );
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const ask = await screen.findByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask });
    await waitFor(() => expect(ask).toBeChecked());
    expect(screen.queryByText(enMessages.aiChatPanel.approvalMode.autoNote)).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto }));

    await waitFor(() => expect(puts).toEqual([{ approval_mode: "auto" }]));
    expect(await screen.findByText(enMessages.aiChatPanel.approvalMode.autoNote)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto })).toBeChecked(),
    );
  });

  it("the approval card's 'don't ask again' approves with the conversation flag", async () => {
    configuredWith("ask");
    const pending = {
      ...CREATE_PAGE_CALL,
      id: "tc2",
      name: "delete_page",
      args: { page_id: "p1" },
      destructive: true,
      requires_approval: true,
      system_gated: false,
    };
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
    await user.click(await screen.findByRole("button", { name: enMessages.aiApprovalCard.approveAll }));
    expect(mockApprove).toHaveBeenCalledWith("tc2", "approve", { autoApproveConversation: true });
  });

  it("the approval card hides 'don't ask again' for a system-gated call", async () => {
    configuredWith("auto");
    const pending = {
      ...CREATE_PAGE_CALL,
      id: "tc3",
      name: "restart_system",
      args: {},
      title: "Restart system",
      destructive: true,
      requires_approval: true,
      system_gated: true,
    };
    hookResult = {
      ...defaultHookResult,
      status: "awaiting_approval",
      pendingApproval: pending,
      messages: [
        { role: "user", content: "restart" },
        { role: "assistant", content: "Restarting.", toolCalls: [{ ...pending, phase: "awaiting_approval" }] },
      ],
    };
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: enMessages.aiApprovalCard.approveAll })).not.toBeInTheDocument();
  });

  it("the timeline badges a call that ran without asking", async () => {
    configuredWith("auto");
    hookResult = {
      ...defaultHookResult,
      status: "streaming",
      messages: [
        { role: "user", content: "delete it" },
        {
          role: "assistant",
          content: "",
          pending: true,
          status: { phase: "thinking", toolCallId: null },
          toolCalls: [
            {
              ...CREATE_PAGE_CALL,
              id: "tc2",
              name: "delete_page",
              args: { page_id: "p1" },
              destructive: true,
              requires_approval: true,
              auto_approved: true,
              phase: "ok",
            },
            { ...CREATE_PAGE_CALL, id: "tc4", phase: "ok" },
          ],
        },
      ],
    };
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const timeline = await screen.findByTestId("ai-step-timeline");
    const badges = within(timeline).getAllByRole("button", { name: enMessages.aiChatPanel.autoApproved.badge });
    expect(badges).toHaveLength(1);
    expect(badges[0]).not.toHaveAttribute("aria-label");
  });

  it("the persistent tool-call card badges an auto-approved call too, as plain text with the explanation", async () => {
    configuredWith("auto");
    hookResult = {
      ...defaultHookResult,
      status: "idle",
      messages: [
        { role: "user", content: "delete it" },
        {
          role: "assistant",
          content: "Gone.",
          toolCalls: [
            {
              ...CREATE_PAGE_CALL,
              id: "tc2",
              name: "delete_page",
              args: { page_id: "p1" },
              destructive: true,
              requires_approval: true,
              auto_approved: true,
              phase: "ok",
            },
            { ...CREATE_PAGE_CALL, id: "tc4", phase: "ok" },
          ],
        },
      ],
    };
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    expect(screen.queryByTestId("ai-step-timeline")).not.toBeInTheDocument();
    const deleteCard = await screen.findByTestId("ai-tool-delete_page");
    expect(deleteCard).toHaveTextContent(enMessages.aiChatPanel.autoApproved.badge);
    expect(deleteCard).toHaveTextContent(enMessages.aiChatPanel.autoApproved.tooltip);
    // A card's header is one button (the collapsible trigger): the badge
    // there is text, never a nested control.
    expect(within(deleteCard).queryByRole("button", { name: enMessages.aiChatPanel.autoApproved.badge })).toBeNull();
    expect(screen.getByTestId("ai-tool-create_page")).not.toHaveTextContent(enMessages.aiChatPanel.autoApproved.badge);
  });

  it("after 'don't ask again' the pill reads Auto with a this-chat caption, and Ask turns it back off", async () => {
    configuredWith("ask");
    const puts: unknown[] = [];
    server.use(
      http.put(`${API_BASE}/settings/ai`, async ({ request }) => {
        puts.push(await request.json());
        return HttpResponse.json({ ...CONFIGURED, providers: [CONFIGURED_PROVIDER] });
      }),
    );
    hookResult = { ...defaultHookResult, autoApprove: true, messages: [{ role: "user", content: "hi" }] };
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto })).toBeChecked(),
    );
    // The caption waits for the install setting to load (it is "this chat
    // only" relative to that setting).
    expect(await screen.findByText(enMessages.aiChatPanel.approvalMode.thisChat)).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask }));

    expect(mockDisableAutoApprove).toHaveBeenCalledTimes(1);
    // The install setting is already Ask: nothing to PUT.
    expect(puts).toEqual([]);
  });

  it("with the install in Auto, 'don't ask again' shows no this-chat caption", async () => {
    configuredWith("auto");
    hookResult = { ...defaultHookResult, autoApprove: true };
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    // Wait until the settings GET has landed (the composer unlocks on it),
    // so the absence below is judged against the loaded install setting.
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto })).toBeChecked();
    expect(screen.queryByText(enMessages.aiChatPanel.approvalMode.thisChat)).not.toBeInTheDocument();
  });

  it("a failed PUT shows no Auto note and leaves the pill on Ask", async () => {
    configuredWith("ask");
    server.use(http.put(`${API_BASE}/settings/ai`, () => HttpResponse.json({ detail: "nope" }, { status: 500 })));
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const ask = await screen.findByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask });
    await waitFor(() => expect(ask).toBeChecked());
    await user.click(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask })).toBeChecked(),
    );
    expect(screen.queryByText(enMessages.aiChatPanel.approvalMode.autoNote)).not.toBeInTheDocument();
  });

  it("the pill stays enabled while the PUT is in flight so the activated radio keeps focus", async () => {
    configuredWith("ask");
    server.use(http.put(`${API_BASE}/settings/ai`, () => new Promise<never>(() => {})));
    const user = userEvent.setup();
    render(<AiChatPanel {...defaultProps} />, { wrapper: Wrapper });
    const ask = await screen.findByRole("radio", { name: enMessages.aiChatPanel.approvalMode.ask });
    await waitFor(() => expect(ask).toBeChecked());
    const auto = screen.getByRole("radio", { name: enMessages.aiChatPanel.approvalMode.auto });
    await user.click(auto);
    expect(auto).toBeChecked();
    expect(auto).not.toBeDisabled();
    expect(auto).toHaveFocus();
  });
});
