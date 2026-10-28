/**
 * Pages is a section: the page editor opens under "Pages › <page name>"
 * inside the Pages card, instead of sliding up as a separate full screen.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagesSection } from "../../app/routes/pages";
import { server } from "./mocks/server";

const route = { pathname: "/pages", params: {} as Record<string, string>, search: "" };

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useParams: () => route.params,
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
}));

function mockPages() {
  server.use(
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [{ id: "p1", name: "Morning briefing", type: "template", device_type: "flagship" }],
        total: 1,
      }),
    ),
  );
}

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PagesSection>
        <p>body</p>
      </PagesSection>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  route.pathname = "/pages";
  route.params = {};
  route.search = "";
  mockPages();
});

describe("/pages section", () => {
  it("is just the Pages header at the list", () => {
    renderSection();
    expect(screen.getByRole("heading", { level: 1, name: "Pages" })).toBeInTheDocument();
    expect(document.querySelector("[data-slot=page-subheader]")).toHaveAttribute("data-state", "closed");
  });

  it("names the page being edited under a breadcrumb back to Pages", async () => {
    route.pathname = "/pages/edit/p1";
    route.params = { id: "p1" };
    renderSection();
    expect(await screen.findByRole("heading", { level: 2, name: "Morning briefing" })).toBeInTheDocument();
    const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(trail).getByRole("link", { name: "Pages" })).toHaveAttribute("href", "/pages");
  });

  it("reads the page from ?id= on the query-string editor route", async () => {
    route.pathname = "/pages/edit";
    route.search = "id=p1";
    renderSection();
    expect(await screen.findByRole("heading", { level: 2, name: "Morning briefing" })).toBeInTheDocument();
  });

  it("calls a page that is still being made a new page", () => {
    route.pathname = "/pages/new";
    renderSection();
    expect(screen.getByRole("heading", { level: 2, name: "New Page" })).toBeInTheDocument();
  });
});
