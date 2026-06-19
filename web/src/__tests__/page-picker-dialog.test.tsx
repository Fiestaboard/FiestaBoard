import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PagePickerDialog } from "@/components/page-picker-dialog";

const PAGES = [
  { id: "page-1", name: "Morning Report", type: "template" },
  { id: "page-2", name: "Weather Now", type: "template" },
  { id: "page-3", name: "Countdown", type: "template" },
];

// Collection IDs must use the "collection:" prefix (see lib/api.ts COLLECTION_ID_PREFIX)
const COLLECTION_ID = "collection:abc";

describe("PagePickerDialog", () => {
  it("renders all provided page names", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId={null} onSelect={vi.fn()} />);

    expect(screen.getByText("Morning Report")).toBeInTheDocument();
    expect(screen.getByText("Weather Now")).toBeInTheDocument();
    expect(screen.getByText("Countdown")).toBeInTheDocument();
  });

  it("marks the currently selected page as aria-selected", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId="page-2" onSelect={vi.fn()} />);

    const options = screen.getAllByRole("option");
    const selected = options.find((o) => o.getAttribute("aria-selected") === "true");
    expect(selected).toBeDefined();
    expect(selected).toHaveTextContent("Weather Now");
  });

  it("calls onSelect with the page id when a page button is clicked", () => {
    const onSelect = vi.fn();
    render(<PagePickerDialog pages={PAGES} selectedPageId={null} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Morning Report"));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("page-1");
  });

  it("calls onSelect when a different page is clicked while one is selected", () => {
    const onSelect = vi.fn();
    render(<PagePickerDialog pages={PAGES} selectedPageId="page-1" onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Countdown"));
    expect(onSelect).toHaveBeenCalledWith("page-3");
  });

  it("shows 'None' option when allowNone is true", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId="page-1" onSelect={vi.fn()} allowNone />);

    expect(screen.getByText("None (no default)")).toBeInTheDocument();
  });

  it("does not show 'None' option when allowNone is false (default)", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId={null} onSelect={vi.fn()} />);

    expect(screen.queryByText("None (no default)")).not.toBeInTheDocument();
  });

  it("calls onSelect(null) when None option is clicked", () => {
    const onSelect = vi.fn();
    render(<PagePickerDialog pages={PAGES} selectedPageId="page-1" onSelect={onSelect} allowNone />);

    fireEvent.click(screen.getByText("None (no default)"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("shows an empty state when no pages are provided", () => {
    render(<PagePickerDialog pages={[]} selectedPageId={null} onSelect={vi.fn()} />);

    expect(screen.getByText("No pages yet")).toBeInTheDocument();
  });

  it("shows page type badges when type is provided", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId={null} onSelect={vi.fn()} />);

    const templateBadges = screen.getAllByText("template");
    expect(templateBadges.length).toBeGreaterThan(0);
  });

  it("renders a listbox with aria-label for accessibility", () => {
    render(<PagePickerDialog pages={PAGES} selectedPageId={null} onSelect={vi.fn()} />);

    expect(screen.getByRole("listbox", { name: /pages/i })).toBeInTheDocument();
  });

  it("shows tabs when collections are provided", () => {
    const collections = [
      {
        id: COLLECTION_ID,
        name: "Rotating Display",
        page_ids: ["page-1", "page-2"],
        selection_mode: "time" as const,
        time: { interval_seconds: 30 },
        variable: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    render(<PagePickerDialog pages={PAGES} collections={collections} selectedPageId={null} onSelect={vi.fn()} />);

    expect(screen.getByRole("tab", { name: /pages/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /collections/i })).toBeInTheDocument();
  });

  it("renders collection tab with correct count when collections are provided", () => {
    const collections = [
      {
        id: COLLECTION_ID,
        name: "Morning Collection",
        page_ids: ["page-1"],
        selection_mode: "time" as const,
        time: { interval_seconds: 30 },
        variable: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    render(<PagePickerDialog pages={PAGES} collections={collections} selectedPageId={null} onSelect={vi.fn()} />);

    const collectionsTab = screen.getByRole("tab", { name: /collections/i });
    expect(collectionsTab).toBeInTheDocument();
    // Tab label should include the count "1"
    expect(collectionsTab).toHaveTextContent("1");
  });

  it("marks decorative tab icons as aria-hidden so screen readers don't announce them", () => {
    const collections = [
      {
        id: COLLECTION_ID,
        name: "Rotating Display",
        page_ids: ["page-1", "page-2"],
        selection_mode: "time" as const,
        time: { interval_seconds: 30 },
        variable: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    render(<PagePickerDialog pages={PAGES} collections={collections} selectedPageId={null} onSelect={vi.fn()} />);

    // Tabs already have visible text labels, so the Lucide icons inside
    // them are decorative — they must be hidden from AT (WCAG 2.2 AA 1.1.1).
    for (const tabName of [/pages/i, /collections/i]) {
      const tab = screen.getByRole("tab", { name: tabName });
      const svg = tab.querySelector("svg");
      expect(svg).not.toBeNull();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("defaults to collections tab when a collection id is selected", () => {
    const collections = [
      {
        id: COLLECTION_ID,
        name: "Morning Collection",
        page_ids: ["page-1"],
        selection_mode: "time" as const,
        time: { interval_seconds: 30 },
        variable: null,
        created_at: "2025-01-01T00:00:00Z",
      },
    ];
    render(
      <PagePickerDialog pages={PAGES} collections={collections} selectedPageId={COLLECTION_ID} onSelect={vi.fn()} />,
    );

    // When a collection ID is selected, the collections tab should be active
    const collectionsTab = screen.getByRole("tab", { name: /collections/i });
    expect(collectionsTab).toHaveAttribute("data-state", "active");
  });
});
