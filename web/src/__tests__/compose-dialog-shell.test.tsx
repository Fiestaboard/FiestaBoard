// BB-FH-1, BB-FH-3, BB-FH-4: Compose's shell against 07a.
// Desktop `311:72982`: the 560 px Dialog shell (20 px title, 40 px close), a
// plain 3-line Textarea, and a Tile sm preview that hugs the board.
// Phone `310:25531`: no Show on picker (the header's display is the target),
// the short description, a plain field with no counter, and Show now first so
// it sits above the fold.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
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

async function draw(phone: boolean) {
  asPhone(phone);
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
          scheduleEnabled
          showOn={{
            value: "kitchen",
            onValueChange: vi.fn(),
            options: [
              { id: "kitchen", label: "Kitchen board · Flagship 22 × 6" },
              { id: "hallway", label: "Hallway Note · Note 15 × 3" },
            ],
          }}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return screen.findByRole("dialog", { name: /compose a message/i });
}

afterEach(() => vi.restoreAllMocks());

describe("Compose on desktop (BB-FH-1, BB-FH-4)", () => {
  it("uses the 560 px wide Dialog shell", async () => {
    const dialog = await draw(false);
    expect(dialog).toHaveAttribute("data-variant", "wide");
  });

  it("takes the message in a plain 3-line textarea, not the template editor", async () => {
    const dialog = await draw(false);
    const message = within(dialog).getByLabelText(/^message$/i);
    expect(message).toHaveAttribute("data-slot", "textarea");
    expect(message).toHaveAttribute("rows", "3");
    expect(message.className).not.toMatch(/font-mono|uppercase/);
    expect(within(dialog).getByText(/0 of 6 lines · longest line 0 of 22 characters/)).toBeInTheDocument();
  });

  it("previews at Tile sm with a bezel that hugs the board", async () => {
    const dialog = await draw(false);
    expect(dialog.querySelector('[data-layout="phone-hero"]')).not.toBeNull();
  });

  it("keeps the Show on picker", async () => {
    const dialog = await draw(false);
    expect(within(dialog).getByRole("combobox", { name: /show on/i })).toBeInTheDocument();
  });
});

describe("Compose on a phone (BB-FH-3)", () => {
  it("has no Show on picker and names the header's display", async () => {
    const sheet = await draw(true);
    expect(within(sheet).queryByRole("combobox", { name: /show on/i })).toBeNull();
    expect(
      within(sheet).getByText("Shows on Kitchen board (the display in the header) when you choose Show now."),
    ).toBeInTheDocument();
  });

  it("takes the message in a plain textarea with no counter line", async () => {
    const sheet = await draw(true);
    expect(within(sheet).getByLabelText(/^message$/i)).toHaveAttribute("data-slot", "textarea");
    expect(within(sheet).queryByText(/of 6 lines/)).toBeNull();
  });

  it("puts Show now first among the actions, with no Cancel", async () => {
    const sheet = await draw(true);
    const actions = sheet.querySelector('[data-slot="compose-actions"]') as HTMLElement;
    const buttons = within(actions).getAllByRole("button");
    expect(buttons[0]).toHaveAccessibleName(/^show now$/i);
    expect(within(actions).queryByRole("button", { name: /^cancel$/i })).toBeNull();
  });
});
