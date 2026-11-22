import { screen, waitFor } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";
import { expect, vi } from "vitest";

/** Exercise the list-detail boundary in jsdom, where viewport media defaults false. */
export function integrationDesktop() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(min-width: 768px)",
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
export async function openIntegration(user: ReturnType<typeof userEvent.setup>, tab?: "Variables") {
  await waitFor(() => expect(document.querySelector('button[data-slot="list-row"]')).not.toBeNull());
  await user.click(document.querySelector<HTMLButtonElement>('button[data-slot="list-row"]')!);
  if (tab) await user.click(await screen.findByRole("tab", { name: tab }));
}

/** The section header's menu, which also holds the open detail pane's actions (BB-FC-9). */
export async function openIntegrationOptions(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Integration options" }));
}
