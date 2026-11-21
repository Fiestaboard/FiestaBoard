// BB-FH-2 (07a `310:20287` / `310:25531` "Typing"): Compose opens with the
// caret in Message. Landing on the "Show on" select made the first keystroke
// typeahead-pick another display, so the message went somewhere else.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

function asPhone(phone: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: phone && query.includes("max-width"),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

function draw(onShowOn = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        <ComposePageDialog
          open
          onOpenChange={vi.fn()}
          deviceType="flagship"
          targetBoardLabel="Kitchen board"
          sendBoardId="kitchen"
          showOn={{
            value: "kitchen",
            onValueChange: onShowOn,
            options: [
              { id: "kitchen", label: "Kitchen board · Flagship 22 × 6" },
              { id: "hallway", label: "Hallway Note · Note 15 × 3" },
            ],
          }}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return onShowOn;
}

describe("Compose opens in the message field (BB-FH-2)", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([
    ["desktop", false],
    ["phone", true],
  ])("on %s the caret starts in Message and typing goes there", async (_name, phone) => {
    asPhone(phone);
    const onShowOn = draw();
    const dialog = await screen.findByRole("dialog", { name: /compose a message/i });
    const message = within(dialog).getByLabelText(/^message$/i);
    await waitFor(() => expect(document.activeElement).toBe(message));

    await userEvent.keyboard("HELLO");
    expect(message).toHaveValue("HELLO");
    expect(onShowOn).not.toHaveBeenCalled();
  });
});
