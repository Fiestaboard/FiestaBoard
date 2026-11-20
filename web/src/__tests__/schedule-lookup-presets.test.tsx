/** BB-C-6: "Which page at…" never offers a quick moment that has already passed. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ScheduleLookup } from "@/components/schedule/schedule-lookup";

function renderAt(iso: string) {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(iso));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ScheduleLookup boardId="display-2" pages={[]} collections={[]} timezone="UTC" />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.useRealTimers());

it("drops Tonight once 9:00 PM has passed", () => {
  renderAt("2026-11-20T23:54:00Z");
  expect(screen.queryByRole("radio", { name: "Tonight 9:00 PM" })).not.toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Tomorrow 3:00 PM" })).toBeInTheDocument();
});

it("offers Tonight earlier in the evening", () => {
  renderAt("2026-11-20T18:00:00Z");
  expect(screen.getByRole("radio", { name: "Tonight 9:00 PM" })).toBeInTheDocument();
});

it("moves Saturday 12:30 PM to next week once this Saturday's has passed", () => {
  renderAt("2026-11-21T13:00:00Z");
  fireEvent.click(screen.getByRole("radio", { name: "Sat 12:30 PM" }));
  expect(screen.getByLabelText("Instant")).toHaveValue("2026-11-28T12:30");
});
