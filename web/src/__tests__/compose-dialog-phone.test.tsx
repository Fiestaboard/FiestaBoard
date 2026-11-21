import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

function asPhone(phone = true) {
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

function draw(onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        <ComposePageDialog open onOpenChange={onOpenChange} deviceType="flagship" scheduleEnabled />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

// BB-A-3 (07a `310:25531`): on a phone Compose is a bottom sheet with a
// grabber. The sheet scrolls as one, so the duration choice is part of the
// flow instead of hidden below an inner scroller's fold.
describe("ComposePageDialog on a phone", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is a bottom sheet with a grabber and a left-aligned title", async () => {
    asPhone();
    draw();
    const sheet = await screen.findByRole("dialog", { name: /compose a message/i });
    expect(sheet).toHaveAttribute("data-slot", "sheet-content");
    expect(sheet.querySelector('[data-slot="sheet-grabber"]')).not.toBeNull();
    expect(within(sheet).getByText(/how long should it stay up/i)).toBeInTheDocument();
  });

  it("has no inner scroller cutting the preview off", async () => {
    asPhone();
    draw();
    const sheet = await screen.findByRole("dialog", { name: /compose a message/i });
    // The sheet's own body is the one scroller; the duration step sits in it.
    const duration = within(sheet).getByText(/how long should it stay up/i);
    expect(duration.closest(".overflow-y-auto")).toHaveAttribute("data-slot", "sheet-body");
    // Review M2 (#2559): Show now comes after the duration, in the same flow.
    const show = within(sheet).getByRole("button", { name: /^show now$/i });
    expect(duration.compareDocumentPosition(show) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(show.closest('[data-slot="sheet-body"]')).not.toBeNull();
    expect(sheet.querySelector('[data-layout="phone-hero"]')).not.toBeNull();
  });

  it("gives the actions full-width touch-size buttons", async () => {
    asPhone();
    draw();
    const sheet = await screen.findByRole("dialog", { name: /compose a message/i });
    const show = within(sheet).getByRole("button", { name: /^show now$/i });
    expect(show).toHaveAttribute("data-size", "touch");
  });

  it("closes on Back instead of leaving Home (BB-A-12)", async () => {
    asPhone();
    const onOpenChange = vi.fn();
    draw(onOpenChange);
    await screen.findByRole("dialog", { name: /compose a message/i });
    act(() => {
      // Back: the browser is now on the entry below the sheet's.
      window.history.replaceState(null, "");
      window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("stays a centred dialog on a wide screen", async () => {
    asPhone(false);
    draw();
    const dialog = await screen.findByRole("dialog", { name: /compose a message/i });
    expect(dialog).not.toHaveAttribute("data-slot", "sheet-content");
  });
});
