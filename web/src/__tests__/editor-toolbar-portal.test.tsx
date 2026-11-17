import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

it("portals the phone toolbar out of the editor's contained layout", () => {
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
  expect(screen.getByRole("group", { name: "Editor tools" }).parentElement).toBe(document.body);
  unmount();
  host.remove();
});
