// Tests for ComposePageDialog — the one-off "send a message without saving it"
// surface from issue #1787.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

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
    expect(screen.getByRole("button", { name: /send to board/i })).toBeDisabled();
  });

  it("Send is enabled once the message has content", async () => {
    renderDialog();
    typeMessage("HELLO");
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
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
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /send to board/i }));

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
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /send to board/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ device_type: "note" });
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
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /send to board/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("saving is optional — sending never creates a page", async () => {
    let pageCreated = false;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, () =>
        HttpResponse.json({ active: true, template: ["HI"], device_type: "flagship" }),
      ),
      http.post(`${API_BASE}/pages`, () => {
        pageCreated = true;
        return HttpResponse.json({ status: "success", page: { id: "p", name: "x" } });
      }),
    );

    renderDialog();
    typeMessage("HI");
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /send to board/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    expect(pageCreated).toBe(false);
  });

  it("Save as Page creates a page with the composed template and does not send an override", async () => {
    let capturedPage: Record<string, unknown> | null = null;
    let overrideSent = false;
    server.use(
      http.post(`${API_BASE}/pages`, async ({ request }) => {
        capturedPage = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "success", page: { id: "p1", name: "Saved" } });
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
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /send to board/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeEnabled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("warns when the message has more lines than the board can show", async () => {
    renderDialog({ deviceType: "note" });
    typeMessage("A\nB\nC\nD");
    await waitFor(() => expect(screen.getByText(/too many lines/i)).toBeInTheDocument());
  });

  it("does not send a message that is longer than the board", async () => {
    renderDialog({ deviceType: "note" });
    typeMessage("A\nB\nC\nD");
    await waitFor(() => expect(screen.getByRole("button", { name: /send to board/i })).toBeDisabled());
  });
});
