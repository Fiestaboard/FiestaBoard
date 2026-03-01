import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PageGridSelector } from "@/components/page-grid-selector";
import { api } from "@/lib/api";
import type { PagePreviewBatchResponse, Page } from "@/lib/api";

// Mock the API
vi.mock("@/lib/api", () => ({
  api: {
    getPages: vi.fn(),
    getBoardSettings: vi.fn(),
    previewPagesBatch: vi.fn(),
    getCarousels: vi.fn(),
  },
  isCarouselId: (id: string) => id?.startsWith("carousel:"),
  CAROUSEL_ID_PREFIX: "carousel:",
}));

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
});

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

// Mock data
const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Page 1",
    template: "Test Template 1",
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Page 2",
    template: "Test Template 2",
    updated_at: "2024-01-02T00:00:00Z",
  },
  {
    id: "page-3",
    name: "Page 3",
    template: "Test Template 3",
    updated_at: "2024-01-03T00:00:00Z",
  },
];

const mockBatchPreviewResponse: PagePreviewBatchResponse = {
  previews: {
    "page-1": {
      page_id: "page-1",
      message: "Preview Message 1",
      lines: ["Line 1", "Line 2"],
      available: true,
    },
    "page-2": {
      page_id: "page-2",
      message: "Preview Message 2",
      lines: ["Line 3", "Line 4"],
      available: true,
    },
    "page-3": {
      page_id: "page-3",
      message: "Preview Message 3",
      lines: ["Line 5", "Line 6"],
      available: true,
    },
  },
  total: 3,
  successful: 3,
};

describe("PageGridSelector", () => {
  beforeEach(() => {
    // Clear mocks and localStorage before each test
    vi.clearAllMocks();
    localStorageMock.clear();

    // Setup default mock responses
    vi.mocked(api.getPages).mockResolvedValue({
      pages: mockPages,
      total: mockPages.length,
    });

    vi.mocked(api.getBoardSettings).mockResolvedValue({
      board_type: "black",
      boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
      devices: ["flagship"],
    });

    vi.mocked(api.getCarousels).mockResolvedValue({
      carousels: [],
      total: 0,
    });

    vi.mocked(api.previewPagesBatch).mockResolvedValue(mockBatchPreviewResponse);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders page buttons for all pages", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(screen.getByText("Page 1")).toBeInTheDocument();
      expect(screen.getByText("Page 2")).toBeInTheDocument();
      expect(screen.getByText("Page 3")).toBeInTheDocument();
    });
  });

  it("calls previewPagesBatch with all page IDs", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(api.previewPagesBatch).toHaveBeenCalledWith([
        "page-1",
        "page-2",
        "page-3",
      ]);
    });
  });

  it("caches preview data in localStorage", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      const cached = localStorageMock.getItem("fiestaboard_previews_batch");
      expect(cached).toBeTruthy();
      
      if (cached) {
        const parsedCache = JSON.parse(cached);
        expect(parsedCache["page-1"]).toBeDefined();
        expect(parsedCache["page-1"].preview.message).toBe("Preview Message 1");
        expect(parsedCache["page-1"].pageUpdatedAt).toBe("2024-01-01T00:00:00Z");
      }
    });
  });

  it("uses cached previews on subsequent renders", async () => {
    // Pre-populate cache
    const cachedData = {
      "page-1": {
        preview: mockBatchPreviewResponse.previews["page-1"],
        pageUpdatedAt: "2024-01-01T00:00:00Z",
        cachedAt: new Date().toISOString(),
      },
      "page-2": {
        preview: mockBatchPreviewResponse.previews["page-2"],
        pageUpdatedAt: "2024-01-02T00:00:00Z",
        cachedAt: new Date().toISOString(),
      },
      "page-3": {
        preview: mockBatchPreviewResponse.previews["page-3"],
        pageUpdatedAt: "2024-01-03T00:00:00Z",
        cachedAt: new Date().toISOString(),
      },
    };
    localStorageMock.setItem("fiestaboard_previews_batch", JSON.stringify(cachedData));

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    // Wait for pages to load
    await waitFor(() => {
      expect(screen.getByText("Page 1")).toBeInTheDocument();
    });

    // previewPagesBatch should not be called since cache is valid
    expect(api.previewPagesBatch).not.toHaveBeenCalled();
  });

  it("invalidates cache when page updated_at changes", async () => {
    // Pre-populate cache with old timestamp
    const cachedData = {
      "page-1": {
        preview: mockBatchPreviewResponse.previews["page-1"],
        pageUpdatedAt: "2023-12-01T00:00:00Z", // Old timestamp
        cachedAt: new Date().toISOString(),
      },
    };
    localStorageMock.setItem("fiestaboard_previews_batch", JSON.stringify(cachedData));

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    // previewPagesBatch should be called for page-1 since cache is stale
    await waitFor(() => {
      expect(api.previewPagesBatch).toHaveBeenCalled();
      const callArgs = vi.mocked(api.previewPagesBatch).mock.calls[0][0];
      expect(callArgs).toContain("page-1");
    });
  });

  it("handles batch preview errors gracefully", async () => {
    vi.mocked(api.previewPagesBatch).mockRejectedValue(
      new Error("Network error")
    );

    // Spy on console.error to suppress error output in tests
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    // Should still render page buttons even if preview fails
    await waitFor(() => {
      expect(screen.getByText("Page 1")).toBeInTheDocument();
      expect(screen.getByText("Page 2")).toBeInTheDocument();
      expect(screen.getByText("Page 3")).toBeInTheDocument();
    });

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to fetch batch previews:",
      expect.any(Error)
    );

    consoleErrorSpy.mockRestore();
  });

  it("handles partial batch failures", async () => {
    const partialResponse: PagePreviewBatchResponse = {
      previews: {
        "page-1": {
          page_id: "page-1",
          message: "Preview Message 1",
          lines: ["Line 1", "Line 2"],
          available: true,
        },
        "page-2": {
          page_id: "page-2",
          message: "",
          lines: [],
          available: false,
          error: "Page rendering failed",
        },
        "page-3": {
          page_id: "page-3",
          message: "Preview Message 3",
          lines: ["Line 5", "Line 6"],
          available: true,
        },
      },
      total: 3,
      successful: 2,
    };

    vi.mocked(api.previewPagesBatch).mockResolvedValue(partialResponse);

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    // Should still render all pages
    await waitFor(() => {
      expect(screen.getByText("Page 1")).toBeInTheDocument();
      expect(screen.getByText("Page 2")).toBeInTheDocument();
      expect(screen.getByText("Page 3")).toBeInTheDocument();
    });

    // Check that only available previews were cached
    await waitFor(() => {
      const cached = localStorageMock.getItem("fiestaboard_previews_batch");
      if (cached) {
        const parsedCache = JSON.parse(cached);
        expect(parsedCache["page-1"]).toBeDefined();
        expect(parsedCache["page-3"]).toBeDefined();
        // page-2 should not be cached since it's not available
        expect(parsedCache["page-2"]).toBeUndefined();
      }
    });
  });

  it("shows empty state when no pages exist", async () => {
    vi.mocked(api.getPages).mockResolvedValue({
      pages: [],
      total: 0,
    });

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(screen.getByText("No pages created yet.")).toBeInTheDocument();
      expect(screen.getByText("Create your first page")).toBeInTheDocument();
    });

    // Should not call batch preview for empty list
    expect(api.previewPagesBatch).not.toHaveBeenCalled();
  });

  it("highlights active page", async () => {
    render(
      <PageGridSelector
        activePageId="page-2"
        onSelectPage={vi.fn()}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      const button = screen.getByText("Page 2").closest("button");
      expect(button).toHaveClass("border-primary");
    });
  });

  it("calls onSelectPage when a page is clicked", async () => {
    const onSelectPage = vi.fn();

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={onSelectPage}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      screen.getByText("Page 1").click();
    });

    expect(onSelectPage).toHaveBeenCalledWith("page-1");
  });

  it("disables page buttons when isPending is true", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
        isPending={true}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      const button1 = screen.getByText("Page 1").closest("button");
      const button2 = screen.getByText("Page 2").closest("button");
      expect(button1).toBeDisabled();
      expect(button2).toBeDisabled();
    });
  });

  it("shows custom label when provided", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
        label="CHOOSE A PAGE"
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(screen.getByText("CHOOSE A PAGE")).toBeInTheDocument();
    });
  });

  it("accepts showCarousels prop", async () => {
    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={vi.fn()}
        showCarousels={false}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(screen.getByText("Page 1")).toBeInTheDocument();
    });
  });

  it("renders carousel buttons when carousels exist", async () => {
    vi.mocked(api.getCarousels).mockResolvedValue({
      carousels: [
        {
          id: "carousel:c1",
          name: "My Carousel",
          page_ids: ["page-1", "page-2"],
          interval_seconds: 30,
          created_at: "2025-01-01T00:00:00Z",
        },
        {
          id: "carousel:c2",
          name: "Single Carousel",
          page_ids: ["page-3"],
          interval_seconds: 60,
          created_at: "2025-01-01T00:00:00Z",
        },
      ],
      total: 2,
    });

    const onSelectPage = vi.fn();

    render(
      <PageGridSelector
        activePageId={null}
        onSelectPage={onSelectPage}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      expect(screen.getByText("My Carousel")).toBeInTheDocument();
      expect(screen.getByText("Single Carousel")).toBeInTheDocument();
    });

    expect(screen.getByText("2 pages")).toBeInTheDocument();
    expect(screen.getByText("1 page")).toBeInTheDocument();
  });

  it("highlights active carousel and handles click", async () => {
    vi.mocked(api.getCarousels).mockResolvedValue({
      carousels: [
        {
          id: "carousel:c1",
          name: "Active Carousel",
          page_ids: ["page-1", "page-2"],
          interval_seconds: 30,
          created_at: "2025-01-01T00:00:00Z",
        },
      ],
      total: 1,
    });

    const onSelectPage = vi.fn();

    render(
      <PageGridSelector
        activePageId="carousel:c1"
        onSelectPage={onSelectPage}
      />,
      { wrapper: TestWrapper }
    );

    await waitFor(() => {
      const button = screen.getByText("Active Carousel").closest("button");
      expect(button).toHaveClass("border-primary");
    });

    screen.getByText("Active Carousel").closest("button")!.click();
    expect(onSelectPage).toHaveBeenCalledWith("carousel:c1");
  });

  describe("list view mode", () => {
    it("renders page names in list view without calling previewPagesBatch", async () => {
      render(
        <PageGridSelector
          activePageId={null}
          onSelectPage={vi.fn()}
          viewMode="list"
        />,
        { wrapper: TestWrapper }
      );

      await waitFor(() => {
        expect(screen.getByText("Page 1")).toBeInTheDocument();
        expect(screen.getByText("Page 2")).toBeInTheDocument();
        expect(screen.getByText("Page 3")).toBeInTheDocument();
      });

      // In list mode, batch previews should not be fetched
      expect(api.previewPagesBatch).not.toHaveBeenCalled();
    });

    it("calls onSelectPage when a list item is clicked", async () => {
      const onSelectPage = vi.fn();

      render(
        <PageGridSelector
          activePageId={null}
          onSelectPage={onSelectPage}
          viewMode="list"
        />,
        { wrapper: TestWrapper }
      );

      await waitFor(() => {
        screen.getByText("Page 1").click();
      });

      expect(onSelectPage).toHaveBeenCalledWith("page-1");
    });

    it("highlights active page in list view", async () => {
      render(
        <PageGridSelector
          activePageId="page-2"
          onSelectPage={vi.fn()}
          viewMode="list"
        />,
        { wrapper: TestWrapper }
      );

      await waitFor(() => {
        const button = screen.getByText("Page 2").closest("button");
        expect(button).toHaveClass("border-primary");
      });
    });

    it("shows list skeleton when loading in list mode", async () => {
      vi.mocked(api.getPages).mockReturnValue(new Promise(() => {}));

      const { container } = render(
        <PageGridSelector
          activePageId={null}
          onSelectPage={vi.fn()}
          viewMode="list"
        />,
        { wrapper: TestWrapper }
      );

      await waitFor(() => {
        const busyElement = container.querySelector('[aria-busy="true"]');
        expect(busyElement).toBeInTheDocument();
      });
    });

    it("disables list items when isPending is true", async () => {
      render(
        <PageGridSelector
          activePageId={null}
          onSelectPage={vi.fn()}
          isPending={true}
          viewMode="list"
        />,
        { wrapper: TestWrapper }
      );

      await waitFor(() => {
        const button1 = screen.getByText("Page 1").closest("button");
        const button2 = screen.getByText("Page 2").closest("button");
        expect(button1).toBeDisabled();
        expect(button2).toBeDisabled();
      });
    });
  });
});
