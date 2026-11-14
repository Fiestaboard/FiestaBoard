// Tests for ComposePageDialog — the one-off "send a message without saving it"
// surface from issue #1787.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

import { FIESTAPANEL_LED_MATRIX, FIESTAPANEL_SPLIT_FLAP } from "./mocks/fiestapanel-models";
import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function renderDialog(props: Partial<React.ComponentProps<typeof ComposePageDialog>> = {}) {
  return render(<ComposePageDialog open={true} onOpenChange={vi.fn()} deviceType="flagship" {...props} />, {
    wrapper: TestWrapper,
  });
}

function typeMessage(text: string) {
  const editor = screen.getByRole("textbox", { name: /message/i });
  fireEvent.change(editor, { target: { value: text } });
  return editor;
}

describe("ComposePageDialog", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("renders the compose title", () => {
    renderDialog();
    expect(screen.getByText(/compose a message/i)).toBeInTheDocument();
  });

  it("Send is disabled until something is typed", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /^show now$/i })).toBeDisabled();
  });

  it("Send is enabled once the message has content", async () => {
    renderDialog();
    typeMessage("HELLO");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
  });

  it("sending posts the template inline with no duration, so the override is indefinite", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          active: true,
          page_id: null,
          expires_at: null,
          remaining_seconds: null,
          revert_mode: "schedule",
          revert_page_id: null,
          template: ["HELLO", "WORLD"],
          line_metadata: null,
          device_type: "flagship",
          notes_wide: null,
          notes_tall: null,
        });
      }),
    );

    renderDialog();
    typeMessage("HELLO\nWORLD");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({
      template: ["HELLO", "WORLD"],
      device_type: "flagship",
    });
    expect(capturedBody).not.toHaveProperty("page_id");
    expect(capturedBody).not.toHaveProperty("duration_minutes");
  });

  it("sends the board's own device type so the one-off is composed at the right size", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true, template: ["HI"], device_type: "note" });
      }),
    );

    renderDialog({ deviceType: "note" });
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ device_type: "note" });
  });

  it("sends a panel board's character grid with a panel one-off", async () => {
    // The server refuses a panel override without grid_rows/grid_cols.
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true, template: ["HI"], device_type: "panel" });
      }),
    );

    renderDialog({ deviceType: "panel", gridRows: 12, gridCols: 29 });
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ device_type: "panel", grid_rows: 12, grid_cols: 29 });
    expect(capturedBody).not.toHaveProperty("notes_wide");
  });

  it("lets a panel one-off use every row of the panel's grid", async () => {
    renderDialog({ deviceType: "panel", gridRows: 12, gridCols: 29 });
    typeMessage(Array.from({ length: 12 }, (_, i) => `LINE ${i}`).join("\n"));
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
  });

  it("closes the dialog after a successful send", async () => {
    const onOpenChange = vi.fn();
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, () =>
        HttpResponse.json({ active: true, template: ["HI"], device_type: "flagship" }),
      ),
    );

    renderDialog({ onOpenChange });
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("saving is optional — sending never creates a page", async () => {
    let pageCreated = false;
    let sent = false;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, () => {
        sent = true;
        return HttpResponse.json({ active: true, template: ["HI"], device_type: "flagship" });
      }),
      http.post(`${API_BASE}/v1/pages`, () => {
        pageCreated = true;
        return HttpResponse.json({ id: "p", name: "x" }, { status: 201 });
      }),
    );

    renderDialog();
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    // Wait for the send itself to land: the button is enabled again before
    // the request even starts, and a request still in flight when this test
    // ends is answered by the NEXT test's handlers.
    await waitFor(() => expect(sent).toBe(true));
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    expect(pageCreated).toBe(false);
  });

  it("Save as Page creates a page with the composed template and does not send an override", async () => {
    let capturedPage: Record<string, unknown> | null = null;
    let overrideSent = false;
    server.use(
      http.post(`${API_BASE}/v1/pages`, async ({ request }) => {
        capturedPage = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "p1", name: "Saved" }, { status: 201 });
      }),
      http.post(`${API_BASE}/settings/temporary-override`, () => {
        overrideSent = true;
        return HttpResponse.json({ active: true });
      }),
    );

    renderDialog();
    typeMessage("SAVE ME");
    fireEvent.click(screen.getByRole("button", { name: /save as page/i }));

    const nameInput = await screen.findByRole("textbox", { name: /page name/i });
    fireEvent.change(nameInput, { target: { value: "My One-Off" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(capturedPage).not.toBeNull());
    expect(capturedPage).toMatchObject({
      name: "My One-Off",
      type: "template",
      device_type: "flagship",
      template: ["SAVE ME"],
    });
    expect(overrideSent).toBe(false);
  });

  it("surfaces a send failure without closing the dialog", async () => {
    const onOpenChange = vi.fn();
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, () =>
        HttpResponse.json({ detail: "Board unreachable" }, { status: 500 }),
      ),
    );

    renderDialog({ onOpenChange });
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("says where the message will show, before Show now", () => {
    renderDialog({ targetBoardLabel: "Living Room" });
    expect(
      screen.getByText("Shows on Living Room when you choose Show now. Nothing reaches the board before that."),
    ).toBeInTheDocument();
    expect(screen.getByText("Not sent yet · Living Room")).toBeInTheDocument();
  });

  it("holds the message for the chosen duration on the chosen display (H1, the shared step)", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true });
      }),
    );
    renderDialog({ targetBoardLabel: "Desk", sendBoardId: "desk", scheduleEnabled: true });
    fireEvent.change(screen.getByRole("textbox", { name: /^message$/i }), { target: { value: "FOCUS" } });
    expect(screen.getByRole("radio", { name: "1 hr" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "15 min" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ board_id: "desk", template: ["FOCUS"], duration_minutes: 15 });
  });

  it("never sends an indefinite hold when a chosen next-change chip goes away (M2)", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true });
      }),
    );
    const at = new Date(Date.now() + 2 * 60 * 60_000);
    const props = {
      open: true,
      onOpenChange: vi.fn(),
      deviceType: "flagship" as const,
      scheduleEnabled: true,
      sendBoardId: "kitchen",
    };
    const { rerender } = render(<ComposePageDialog {...props} nextChange={{ at, pageId: null }} />, {
      wrapper: TestWrapper,
    });
    const chip = screen.getByRole("radio", { name: /^Until \d/ });
    fireEvent.click(screen.getByRole("radio", { name: "15 min" }));
    fireEvent.click(chip);
    rerender(<ComposePageDialog {...props} nextChange={null} />);
    expect(screen.getByRole("radio", { name: "1 hr" })).toHaveAttribute("aria-checked", "true");
    typeMessage("HELLO");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^show now$/i }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ board_id: "kitchen", duration_minutes: 60 });
  });

  it("warns when the message has more lines than the board can show", async () => {
    renderDialog({ deviceType: "note" });
    typeMessage("A\nB\nC\nD");
    await waitFor(() => expect(screen.getByText(/too many lines/i)).toBeInTheDocument());
  });

  it("does not send a message that is longer than the board", async () => {
    renderDialog({ deviceType: "note" });
    typeMessage("A\nB\nC\nD");
    await waitFor(() => expect(screen.getByRole("button", { name: /^show now$/i })).toBeDisabled());
  });

  it("previews the message on an LED destination board as its LED matrix", () => {
    renderDialog({ deviceType: "panel", gridRows: 8, gridCols: 10, model: FIESTAPANEL_LED_MATRIX });
    expect(document.querySelector('[data-slot="display-preview"]')).toHaveAttribute("data-technology", "led_matrix");
  });

  it("previews on the flaps for a split-flap destination, as before", () => {
    renderDialog({ model: FIESTAPANEL_SPLIT_FLAP });
    expect(document.querySelector('[data-slot="display-preview"]')).not.toBeInTheDocument();
    expect(document.querySelector("[data-board-preview]")).toBeInTheDocument();
  });
});
