/**
 * SectionShell: a section's card and header stay mounted while its routes
 * drill in and out; a breadcrumb + item heading expand beneath the header.
 */
import { render, screen, within } from "@testing-library/react";
import { Monitor } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { SectionAction, SectionShell, type SectionDetail } from "@/components/section-shell";

const route = { pathname: "/displays" };

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(),
}));

const KITCHEN: SectionDetail = { id: "kitchen", title: "Kitchen", description: "Vestaboard" };

function shell(detail: SectionDetail | null, children: React.ReactNode = <p>body</p>) {
  return (
    <SectionShell
      icon={Monitor}
      title="Displays"
      description="Every board"
      href="/displays"
      action={<button type="button">Add a display</button>}
      detail={detail}
    >
      {children}
    </SectionShell>
  );
}

describe("SectionShell", () => {
  it("names the section in the h1 and offers its action at the hub", () => {
    render(shell(null));
    expect(screen.getByRole("heading", { level: 1, name: "Displays" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a display" }).closest("[inert]")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })?.closest("[inert]")).not.toBeNull();
  });

  it("drills in under the same header: crumb back to the section, the item as h2", () => {
    const { rerender } = render(shell(null));
    const h1 = screen.getByRole("heading", { level: 1 });
    rerender(shell(KITCHEN));
    // The header is the same node — it never remounted.
    expect(screen.getByRole("heading", { level: 1 })).toBe(h1);
    const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(trail).getByRole("link", { name: "Displays" })).toHaveAttribute("href", "/displays");
    expect(screen.getByRole("heading", { level: 2, name: "Kitchen" })).toBeInTheDocument();
    // The list's action belongs to the list; it tucks away with it.
    expect(screen.getByRole("button", { name: "Add a display" }).closest("[inert]")).not.toBeNull();
  });

  it("sends the crumb wherever the detail came from", () => {
    render(shell({ ...KITCHEN, backHref: "/displays?tab=x" }));
    expect(screen.getByRole("link", { name: "Displays" })).toHaveAttribute("href", "/displays?tab=x");
  });

  it("puts a detail page's SectionAction on the sub-header row", () => {
    render(
      shell(
        KITCHEN,
        <SectionAction>
          <button type="button">Remove</button>
        </SectionAction>,
      ),
    );
    const subheader = document.querySelector("[data-slot=page-subheader]")!;
    expect(within(subheader as HTMLElement).getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("renders a SectionAction in place when there is no shell (a page rendered on its own)", () => {
    render(
      <SectionAction>
        <button type="button">Remove</button>
      </SectionAction>,
    );
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("returns focus to the list link that was opened when the route comes back", () => {
    const list = (
      <a href="/displays/kitchen" data-testid="open-kitchen">
        Open Kitchen
      </a>
    );
    route.pathname = "/displays";
    const { rerender } = render(shell(null, list));
    route.pathname = "/displays/kitchen";
    rerender(shell(KITCHEN, <p>detail</p>));
    route.pathname = "/displays";
    rerender(shell(null, list));
    expect(document.activeElement).toBe(screen.getByTestId("open-kitchen"));
  });
});
