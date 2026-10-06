/**
 * The app-level fade runs once per SECTION, not once per URL: a section's
 * layout keeps its own card mounted between its list and its items, and a
 * wrapper keyed by the full pathname would remount it anyway.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PageFadeWrapper, sectionKey } from "@/components/page-fade-wrapper";

const route = { pathname: "/displays" };
vi.mock("@/hooks/use-router", () => ({ usePathname: () => route.pathname }));

describe("sectionKey", () => {
  it("is the first path segment", () => {
    expect(sectionKey("/displays/kitchen")).toBe("/displays");
    expect(sectionKey("/pages/edit/abc")).toBe("/pages");
    expect(sectionKey("/integrations")).toBe("/integrations");
    expect(sectionKey("/")).toBe("/");
  });
});

describe("PageFadeWrapper", () => {
  it("keeps the route subtree mounted while moving within a section", () => {
    route.pathname = "/displays";
    const { rerender } = render(
      <PageFadeWrapper>
        <p data-testid="body">body</p>
      </PageFadeWrapper>,
    );
    const before = screen.getByTestId("body");
    route.pathname = "/displays/kitchen";
    rerender(
      <PageFadeWrapper>
        <p data-testid="body">body</p>
      </PageFadeWrapper>,
    );
    expect(screen.getByTestId("body")).toBe(before);
  });

  it("remounts on a move to another section", () => {
    route.pathname = "/displays";
    const { rerender } = render(
      <PageFadeWrapper>
        <p data-testid="body">body</p>
      </PageFadeWrapper>,
    );
    const before = screen.getByTestId("body");
    route.pathname = "/pages";
    rerender(
      <PageFadeWrapper>
        <p data-testid="body">body</p>
      </PageFadeWrapper>,
    );
    expect(screen.getByTestId("body")).not.toBe(before);
  });
});
