// ComposePageDialog during silence (#1943, #1944): Send is named for what it
// does ("Send now anyway" wakes the board), and when the board holds messages
// "Hold until 7:00 AM" is the primary action — it never wakes the board.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function renderDialog(
  props: Partial<React.ComponentProps<typeof ComposePageDialog>> = {},
  client: QueryClient = makeClient(),
) {
  const onOpenChange = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <ThemeProvider attribute="class" defaultTheme="light">
        <ComposePageDialog open={true} onOpenChange={onOpenChange} deviceType="flagship" {...props} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange, client };
}

function typeMessage(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: /message/i }), { target: { value: text } });
}

function footerButtons() {
  const cancel = screen.getByRole("button", { name: /^cancel$/i });
  const footer = cancel.parentElement as HTMLElement;
  return within(footer)
    .getAllByRole("button")
    .map((b) => b.textContent?.trim());
}

describe("ComposePageDialog during silence", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });

  it("is today's footer when the board is not silenced", () => {
    renderDialog();
    expect(screen.queryByTestId("compose-silence")).not.toBeInTheDocument();
    expect(footerButtons()).toEqual(["Cancel", "Save as Page", "Send to board"]);
  });

  it("with holds on: says when it would show, and Hold is the last (primary) action", () => {
    renderDialog({ silence: { until: "7:00 AM", holds: true } });
    expect(screen.getByTestId("compose-silence")).toHaveTextContent(
      "Hold it and it shows at 7:00 AM, or send it now and the board wakes.",
    );
    expect(footerButtons()).toEqual(["Cancel", "Save as Page", "Send now anyway", "Hold until 7:00 AM"]);
  });

  it("with holds off: warns that sending wakes the board and links to the setting", () => {
    renderDialog({ silence: { until: "7:00 AM", holds: false } });
    const notice = screen.getByTestId("compose-silence");
    expect(notice).toHaveAttribute("data-variant", "warning");
    expect(notice).toHaveTextContent("Sending now wakes the board.");
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute(
      "href",
      "/settings?section=behavior#silence-schedule",
    );
    expect(footerButtons()).toEqual(["Cancel", "Save as Page", "Send now anyway"]);
    expect(screen.queryByTestId("compose-hold")).not.toBeInTheDocument();
  });

  it("Hold posts the lines to the v1 message route — no duration, no override — and closes", async () => {
    let path: string | null = null;
    let body: Record<string, unknown> | null = null;
    let overrideSent = false;
    let statusReads = 0;
    server.use(
      http.post(`${API_BASE}/v1/boards/:board/message`, async ({ request, params }) => {
        path = String(params.board);
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { sent: false, silenced: true, held: true, reason: "Held", board_id: "b1", text: "", characters: [] },
          { status: 202 },
        );
      }),
      http.post(`${API_BASE}/settings/temporary-override`, () => {
        overrideSent = true;
        return HttpResponse.json({ active: true });
      }),
    );
    const client = makeClient();
    // An observed silence-status query, to see the dialog invalidate it.
    client.setQueryDefaults(["silenceStatus"], {
      queryFn: () => {
        statusReads += 1;
        return { active: true };
      },
    });
    void client.fetchQuery({ queryKey: ["silenceStatus"] });
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const { onOpenChange } = renderDialog({ silence: { until: "7:00 AM", holds: true }, targetBoardId: "b1" }, client);
    await waitFor(() => expect(statusReads).toBe(1));

    typeMessage("GOOD\nMORNING");
    fireEvent.click(await screen.findByTestId("compose-hold"));

    await waitFor(() => expect(body).not.toBeNull());
    expect(path).toBe("b1");
    expect(body).toEqual({ lines: ["GOOD", "MORNING"] });
    await waitFor(() => expect(success).toHaveBeenCalledWith("Held — it shows at 7:00 AM"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(overrideSent).toBe(false);
    expect(client.getQueryState(["silenceStatus"])?.isInvalidated).toBe(true);
  });

  it("a refused hold (409) says it could not hold the message", async () => {
    server.use(
      http.post(`${API_BASE}/v1/boards/:board/message`, () =>
        HttpResponse.json({ detail: "Manual sends are blocked while the board is silenced." }, { status: 409 }),
      ),
    );
    const error = vi.spyOn((await import("sonner")).toast, "error");
    const { onOpenChange } = renderDialog({ silence: { until: "7:00 AM", holds: true } });
    typeMessage("HI");
    fireEvent.click(await screen.findByTestId("compose-hold"));
    await waitFor(() => expect(error).toHaveBeenCalledWith("Could not hold the message"));
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("Send now anyway still posts the temporary override, unchanged", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true });
      }),
    );
    renderDialog({ silence: { until: "7:00 AM", holds: true } });
    typeMessage("HI");
    fireEvent.click(await screen.findByTestId("compose-send-anyway"));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ template: ["HI"], device_type: "flagship" });
  });

  it("reopening resets the message", async () => {
    const { rerender, client } = renderDialog({ silence: { until: "7:00 AM", holds: true } });
    typeMessage("HI");
    const reopen = (open: boolean) =>
      rerender(
        <QueryClientProvider client={client}>
          <ThemeProvider attribute="class" defaultTheme="light">
            <ComposePageDialog
              open={open}
              onOpenChange={vi.fn()}
              deviceType="flagship"
              silence={{ until: "7:00 AM", holds: true }}
            />
          </ThemeProvider>
        </QueryClientProvider>,
      );
    reopen(false);
    reopen(true);
    expect(await screen.findByTestId("compose-hold")).toBeDisabled();
  });
});

describe("Compose truthful outcomes", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });
  it("does not say sent or close when a raced hold response reports no write and no hold", async () => {
    server.use(
      http.post(`${API_BASE}/v1/boards/:board/message`, () =>
        HttpResponse.json({ sent: false, silenced: false, held: false }),
      ),
    );
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const info = vi.spyOn((await import("sonner")).toast, "info");
    const { onOpenChange } = renderDialog({ silence: { until: "7:00 AM", holds: true } });
    typeMessage("HI");
    fireEvent.click(screen.getByTestId("compose-hold"));
    await waitFor(() => expect(info).toHaveBeenCalledWith("Nothing was sent (board paused or output set to UI only)"));
    expect(success).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
  it("a paused refresh after a temporary override says nothing was sent", async () => {
    server.use(http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ sent: false })));
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const info = vi.spyOn((await import("sonner")).toast, "info");
    renderDialog({ silence: { until: "7:00 AM", holds: true } });
    typeMessage("HI");
    fireEvent.click(screen.getByTestId("compose-send-anyway"));
    await waitFor(() => expect(info).toHaveBeenCalledWith("Nothing was sent (board paused or output set to UI only)"));
    expect(success).not.toHaveBeenCalledWith("Message sent to board");
  });
});

it("warns before composing for a paused board", () => {
  renderDialog({ silence: { until: "7:00 AM", holds: true }, paused: true });
  expect(screen.getByTestId("compose-paused")).toHaveTextContent(
    "When paused, FiestaBoard does not push anything to this board",
  );
});
