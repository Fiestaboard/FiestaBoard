import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

import { AiPageDialog } from "@/components/ai-page-dialog";

const API_BASE = "/api";

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const CONFIGURED_PROVIDERS = {
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
};

describe("AiPageDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json(CONFIGURED_PROVIDERS),
      ),
    );
  });

  it("renders the prompt textarea and Generate button", async () => {
    render(
      <AiPageDialog
        open
        onOpenChange={vi.fn()}
        deviceType="flagship"
        onInsert={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    expect(
      await screen.findByLabelText("What should the page show?"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /generate/i }),
    ).toBeInTheDocument();
  });

  it("disables Generate until a prompt is entered", async () => {
    render(
      <AiPageDialog
        open
        onOpenChange={vi.fn()}
        deviceType="flagship"
        onInsert={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    // Wait for settings to load so the model dropdown is populated.
    const textarea = (await screen.findByLabelText(
      "What should the page show?",
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /^Generate$/i });
      expect(btn).toBeDisabled();
    });

    fireEvent.change(textarea, { target: { value: "Show the current time" } });

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /^Generate$/i });
      expect(btn).not.toBeDisabled();
    });
  });

  it("calls onInsert with the generated page when Insert is clicked", async () => {
    const onInsert = vi.fn();
    const onOpenChange = vi.fn();
    const generatedPage = {
      name: "Hello",
      type: "template" as const,
      device_type: "flagship" as const,
      template: ["", "Hi", "", "", "", ""],
      line_metadata: Array.from({ length: 6 }, () => ({
        alignment: "center" as const,
        wrap: false,
      })),
      duration_seconds: 60,
    };
    server.use(
      http.post(`${API_BASE}/pages/ai/generate`, () =>
        HttpResponse.json({
          page: generatedPage,
          model_used: "test-model",
          provider_id: "p1",
          warnings: [],
          usage: {},
        }),
      ),
    );

    render(
      <AiPageDialog
        open
        onOpenChange={onOpenChange}
        deviceType="flagship"
        onInsert={onInsert}
      />,
      { wrapper: Wrapper },
    );

    const user = userEvent.setup();
    const textarea = (await screen.findByLabelText(
      "What should the page show?",
    )) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Greet me" } });

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /^Generate$/i });
      expect(btn).not.toBeDisabled();
    });
    await user.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /insert into editor/i }),
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /insert into editor/i }),
    );
    expect(onInsert).toHaveBeenCalledWith(generatedPage);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("surfaces server error message to the user", async () => {
    server.use(
      http.post(
        `${API_BASE}/pages/ai/generate`,
        () =>
          new HttpResponse(
            JSON.stringify({ detail: "Model exploded: foo" }),
            { status: 400, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );

    render(
      <AiPageDialog
        open
        onOpenChange={vi.fn()}
        deviceType="flagship"
        onInsert={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    const user = userEvent.setup();
    const textarea = (await screen.findByLabelText(
      "What should the page show?",
    )) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "x" } });

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /^Generate$/i });
      expect(btn).not.toBeDisabled();
    });
    await user.click(screen.getByRole("button", { name: /^Generate$/i }));

    expect(
      await screen.findByText(/Model exploded: foo/),
    ).toBeInTheDocument();
  });

  it("warns when no AI providers are configured", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: false,
          providers: [],
          default_provider_id: null,
        }),
      ),
    );

    render(
      <AiPageDialog
        open
        onOpenChange={vi.fn()}
        deviceType="flagship"
        onInsert={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    expect(
      await screen.findByText(/no ai providers configured/i),
    ).toBeInTheDocument();
  });
});
