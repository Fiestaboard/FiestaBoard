import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportPageDialog } from "../../app/routes/pages._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
    info: vi.fn(),
    loading: vi.fn(),
  },
  Toaster: () => null,
}));

// Minimal valid share string — a base64url-encoded v1 envelope
const VALID_SHARE_STRING = (() => {
  const envelope = {
    v: 1,
    page: {
      name: "Shared Page",
      type: "template",
      device_type: "flagship",
      template: ["Hello", "", "", "", "", ""],
      duration_seconds: 300,
    },
  };
  return btoa(JSON.stringify(envelope)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
})();

function renderDialog(props: { open?: boolean; onOpenChange?: (v: boolean) => void } = {}) {
  const onOpenChange = props.onOpenChange ?? vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ImportPageDialog open={props.open ?? true} onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );

  return { onOpenChange };
}

describe("ImportPageDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  it("renders title and description when open", () => {
    renderDialog();
    expect(screen.getByText("Import Page")).toBeInTheDocument();
    expect(screen.getByText("Paste a share string to add a page to your collection.")).toBeInTheDocument();
  });

  it("renders textarea and buttons", () => {
    renderDialog();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    renderDialog({ open: false });
    expect(screen.queryByText("Import Page")).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Import button enabled/disabled state
  // ---------------------------------------------------------------------------

  it("Import button is disabled when textarea is empty", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
  });

  it("Import button becomes enabled once text is entered", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox"), "abc");
    expect(screen.getByRole("button", { name: /^import$/i })).toBeEnabled();
  });

  it("Import button is disabled when textarea contains only whitespace", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox"), "   ");
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Cancel
  // ---------------------------------------------------------------------------

  it("calls onOpenChange(false) when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // ---------------------------------------------------------------------------
  // Successful import
  // ---------------------------------------------------------------------------

  it("calls POST /pages/import with the trimmed share string", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/pages/import`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          page: {
            id: "imported-page-1",
            name: "Shared Page",
            type: "template",
            device_type: "flagship",
            template: ["Hello", "", "", "", "", ""],
            duration_seconds: 300,
            created_at: new Date().toISOString(),
          },
        });
      }),
    );

    renderDialog();
    await user.type(screen.getByRole("textbox"), `  ${VALID_SHARE_STRING}  `);
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody!.share_string).toBe(VALID_SHARE_STRING);
  });

  it("shows success toast with the page name on import", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox"), VALID_SHARE_STRING);
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
    expect(mockToastSuccess).toHaveBeenCalledWith(expect.stringContaining("Shared Page"));
  });

  it("closes the dialog on successful import", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog();
    await user.type(screen.getByRole("textbox"), VALID_SHARE_STRING);
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  // ---------------------------------------------------------------------------
  // Error handling
  // ---------------------------------------------------------------------------

  it("shows error toast when the API returns 422", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API_BASE}/pages/import`, () =>
        HttpResponse.json({ detail: "Invalid share string — could not decode." }, { status: 422 }),
      ),
    );

    renderDialog();
    await user.type(screen.getByRole("textbox"), "not-a-valid-share-string");
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    expect(mockToastError).toHaveBeenCalledWith(expect.any(String));
  });

  it("does not close the dialog on error", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API_BASE}/pages/import`, () =>
        HttpResponse.json({ detail: "Invalid share string." }, { status: 422 }),
      ),
    );

    const { onOpenChange } = renderDialog();
    await user.type(screen.getByRole("textbox"), "bad-string");
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  // ---------------------------------------------------------------------------
  // State reset
  // ---------------------------------------------------------------------------

  it("clears textarea when dialog is closed via onOpenChange", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ImportPageDialog open={true} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );

    await user.type(screen.getByRole("textbox"), "some-string");
    expect(screen.getByRole("textbox")).toHaveValue("some-string");

    // Simulate closing and reopening
    rerender(
      <QueryClientProvider client={queryClient}>
        <ImportPageDialog open={false} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={queryClient}>
        <ImportPageDialog open={true} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("textbox")).toHaveValue("");
  });
});
