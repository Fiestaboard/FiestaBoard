/**
 * Pages is a section. The list sits in the Pages card; the page editor
 * replaces it with its own header (back to Pages, the name, Save).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useReportCreatedPage } from "@/components/pages/created-page-context";

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

  // BB-B-4 / BB-B-19 (Figma 57:64661, 316:90600, 184:159319): the editor draws
  // its own header (back to Pages, the name, Save), so the section's card
  // header, breadcrumb and second h2 title are not drawn above it.
  it.each([
    ["/pages/edit/p1", { id: "p1" }, ""],
    ["/pages/edit", {}, "id=p1"],
    ["/pages/new", {}, ""],
  ])(
    "draws no section header, breadcrumb or card above the editor at %s",
    (pathname, params: Record<string, string>, search) => {
      route.pathname = pathname;
      route.params = params;
      route.search = search;
      renderSection();
      expect(screen.queryByRole("heading", { level: 1, name: "Pages" })).not.toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
      expect(document.querySelector("[data-slot=page-card]")).toHaveAttribute("data-surface", "plain");
      expect(screen.getByText("body")).toBeInTheDocument();
    },
  );

  // BB-B-9 (#2563) with the bare editor: after the first save the address
  // shows /pages/edit/{id}, and the editor stays mounted with no section
  // header drawn above it (the editor's own header names the page).
  it("keeps the editor mounted, with no section header, after a new page's first save", async () => {
    route.pathname = "/pages/new";
    function SaveFirst() {
      const report = useReportCreatedPage();
      return (
        <button type="button" onClick={() => report?.("p1")}>
          save
        </button>
      );
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <PagesSection>
          <SaveFirst />
        </PagesSection>
      </QueryClientProvider>,
    );
    const before = screen.getByRole("button", { name: "save" });
    act(() => before.click());
    // The same node: the editor was not remounted by the report.
    await waitFor(() => expect(screen.getByRole("button", { name: "save" })).toBe(before));
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
    expect(document.querySelector("[data-slot=page-card]")).toHaveAttribute("data-surface", "plain");
  });
});
