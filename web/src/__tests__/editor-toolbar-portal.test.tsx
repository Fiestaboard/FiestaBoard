import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

it("keeps portaled phone tools in a named landmark outside the contained editor and cleans up", () => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches: q.includes("max-width"),
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  const host = document.createElement("div");
  host.style.contain = "layout style";
  document.body.appendChild(host);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { unmount } = render(
    <QueryClientProvider client={client}>
      <TemplateEditorToolbar editor={null} container={host} />
    </QueryClientProvider>,
  );
  const region = screen.getByRole("region", { name: "Editor tools" });
  expect(region.parentElement).toBe(document.body);
  expect(within(region).getByRole("group", { name: "Editor tools" })).toBeInTheDocument();
  expect(host).not.toContainElement(region);
  unmount();
  expect(region).not.toBeInTheDocument();
  host.remove();
});
