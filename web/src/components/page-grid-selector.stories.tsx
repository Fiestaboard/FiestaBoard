import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type {
  Collection,
  CollectionsResponse,
  Page,
  PagePreviewBatchEntry,
  PagePreviewBatchResponse,
  PagesResponse,
} from "@/lib/api";

import { PageGridSelector } from "./page-grid-selector";

const meta = {
  title: "Layout/PageGridSelector",
  component: PageGridSelector,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    activePageId: {
      control: "text",
      description: "ID of the currently active page",
    },
    isPending: {
      control: "boolean",
      description: "Whether a page selection is in progress",
    },
    showActiveIndicator: {
      control: "boolean",
      description: "Show active page indicator line",
    },
    label: {
      control: "text",
      description: "Label text above the grid",
    },
  },
} satisfies Meta<typeof PageGridSelector>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages: Page[] = ["Weather Dashboard", "Transit Times", "Morning Briefing", "Evening Summary"].map(
  (name, i) => ({
    id: `page-${i + 1}`,
    name,
    type: "template",
    device_type: "flagship",
    duration_seconds: 300,
    created_at: `2024-01-0${i + 1}T00:00:00Z`,
    updated_at: `2024-01-0${i + 1}T00:00:00Z`,
  }),
);

/** A successful batch-preview entry, matching the endpoint's payload. */
function previewEntry(pageId: string, message: string): PagePreviewBatchEntry {
  return {
    page_id: pageId,
    message,
    lines: message.split("\n"),
    display_type: "template",
    raw: {},
    available: true,
  };
}

const mockPreviews: PagePreviewBatchResponse = {
  previews: {
    "page-1": previewEntry("page-1", "{63}WEATHER{/63}\n{64}72°F SUNNY{/64}\n \nHIGH: 75°F\nLOW: 65°F\nHUMIDITY: 60%"),
    "page-2": previewEntry(
      "page-2",
      "{65}MUNI{/65}\n \n38R  ARRIVES IN 5 MIN\n49   ARRIVES IN 12 MIN\n \nNEXT BART: 8 MIN",
    ),
    "page-3": previewEntry(
      "page-3",
      "{66}GOOD MORNING{/66}\n \nTODAY: FEB 26\nWEATHER: SUNNY 72°F\nMEETINGS: 3\nTRANSIT: ON TIME",
    ),
    "page-4": previewEntry(
      "page-4",
      "{67}EVENING{/67}\n \nSTOCKS: +2.4%\nCALENDAR: CLEAR\nAIR QUALITY: GOOD\nSUNSET: 6:05 PM",
    ),
  },
  total: 4,
  successful: 4,
};

const mockCollections: Collection[] = [
  {
    id: "collection:abc-123",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2", "page-3"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    random: null,
    created_at: "2024-02-01T00:00:00Z",
  },
  {
    id: "collection:def-456",
    name: "Evening Loop",
    page_ids: ["page-3", "page-4"],
    selection_mode: "time",
    time: { interval_seconds: 60 },
    variable: null,
    random: null,
    created_at: "2024-02-02T00:00:00Z",
  },
];

const createQueryClient = (pages: Page[], activePageId?: string, collections?: Collection[]) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });

  client.setQueryData(["pages"], { pages } as PagesResponse);
  client.setQueryData(["pagePreviewBatch", pages.map((p) => p.id)], mockPreviews);
  client.setQueryData(["board-settings"], {
    board_color: "black",
    devices: ["flagship"],
  });
  if (collections) {
    client.setQueryData(["collections"], { collections, total: collections.length } as CollectionsResponse);
  }

  return client;
};

export const Default: Story = {
  args: {
    activePageId: "page-1",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    showActiveIndicator: true,
    label: "SELECT PAGE",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider client={createQueryClient(mockPages, context.args.activePageId || undefined)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const NoActiveIndicator: Story = {
  args: {
    activePageId: "page-2",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    showActiveIndicator: false,
    label: "SELECT PAGE TO EDIT",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider client={createQueryClient(mockPages, context.args.activePageId || undefined)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const WithCustomLabel: Story = {
  args: {
    activePageId: null,
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    label: "CHOOSE A PAGE TO DISPLAY",
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(mockPages)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const PendingState: Story = {
  args: {
    activePageId: "page-1",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    isPending: true,
    label: "SELECT PAGE",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider client={createQueryClient(mockPages, context.args.activePageId || undefined)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const EmptyState: Story = {
  args: {
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    label: "SELECT PAGE",
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient([])}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Loading: Story = {
  args: {
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    label: "SELECT PAGE",
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const ManyPages = () => {
  const manyPages: Page[] = Array.from({ length: 12 }, (_, i) => ({
    id: `page-${i + 1}`,
    name: `Page ${i + 1}`,
    type: "template",
    device_type: "flagship",
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  }));

  return (
    <QueryClientProvider client={createQueryClient(manyPages, "page-3")}>
      <div className="max-w-6xl">
        <PageGridSelector
          activePageId="page-3"
          onSelectPage={(pageId: string) => console.log("Selected:", pageId)}
          label="SELECT PAGE"
        />
      </div>
    </QueryClientProvider>
  );
};

export const WithCollections: Story = {
  args: {
    activePageId: "page-1",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    showActiveIndicator: true,
    showCollections: true,
    label: "SELECT PAGE",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider
        client={createQueryClient(mockPages, context.args.activePageId || undefined, mockCollections)}
      >
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const WithActiveCollection: Story = {
  args: {
    activePageId: "collection:abc-123",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    showActiveIndicator: true,
    showCollections: true,
    label: "SELECT PAGE",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider
        client={createQueryClient(mockPages, context.args.activePageId || undefined, mockCollections)}
      >
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const CollectionsHidden: Story = {
  args: {
    activePageId: "page-1",
    onSelectPage: (pageId: string) => console.log("Selected:", pageId),
    showCollections: false,
    label: "PAGES ONLY",
  },
  decorators: [
    (Story, context) => (
      <QueryClientProvider
        client={createQueryClient(mockPages, context.args.activePageId || undefined, mockCollections)}
      >
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};
