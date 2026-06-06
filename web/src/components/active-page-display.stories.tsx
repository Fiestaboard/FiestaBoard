import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { Collection, CollectionsResponse, Page, PagesResponse, SilenceStatus } from "@/lib/api";

import { ActivePageDisplay } from "./active-page-display";

const meta = {
  title: "Layout/ActivePageDisplay",
  component: ActivePageDisplay,
  parameters: {
    layout: "padded",
    nextjs: {
      appDirectory: true,
      navigation: {
        pathname: "/",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ActivePageDisplay>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Weather Dashboard",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Transit Times",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-02T00:00:00Z",
  },
];

const mockPreviewMessage = "{63}WEATHER{/63}\n{64}72°F SUNNY{/64}\n \nHIGH: 75°F\nLOW: 65°F\nHUMIDITY: 60%";

const mockCollections: Collection[] = [
  {
    id: "collection:abc-123",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    created_at: "2024-02-01T00:00:00Z",
  },
];

const createQueryClient = (
  activePageId: string | null,
  scheduleEnabled: boolean = false,
  silenceActive: boolean = false,
  collections?: Collection[],
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });

  client.setQueryData(["pages"], { pages: mockPages } as PagesResponse);
  client.setQueryData(["activePage"], { page_id: activePageId });
  client.setQueryData(["schedules", "default"], {
    enabled: scheduleEnabled,
    schedules: [],
  });

  if (scheduleEnabled && activePageId) {
    client.setQueryData(["schedules", "active"], {
      page_id: activePageId,
      schedule_id: "sched-1",
    });
  }

  if (activePageId) {
    client.setQueryData(["pagePreview", activePageId], {
      page_id: activePageId,
      message: mockPreviewMessage,
      lines: mockPreviewMessage.split("\n"),
      display_type: "template",
      raw: {},
    });
  }

  // Seed preview data for all pages so collection rotation has something to show
  for (const page of mockPages) {
    if (!client.getQueryData(["pagePreview", page.id])) {
      client.setQueryData(["pagePreview", page.id], {
        page_id: page.id,
        message: mockPreviewMessage,
        lines: mockPreviewMessage.split("\n"),
        display_type: "template",
        raw: {},
      });
    }
  }

  client.setQueryData(["silenceStatus"], {
    enabled: true,
    active: silenceActive,
    start_time_utc: "2024-01-01T00:00:00Z",
    end_time_utc: "2024-01-01T08:00:00Z",
    current_time_utc: "2024-01-01T04:00:00Z",
    next_change_utc: "2024-01-01T08:00:00Z",
  } as SilenceStatus);

  client.setQueryData(["boardSettings"], {
    board_type: "black",
    boards: [],
    devices: ["flagship"],
  });

  client.setQueryData(["collections"], {
    collections: collections ?? [],
    total: collections?.length ?? 0,
  } as CollectionsResponse);

  return client;
};

export const ManualMode: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", false)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const ScheduleMode: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", true)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const SilenceModeActive: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("page-1", false, true)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const ScheduleGap: Story = {
  decorators: [
    (Story) => {
      const client = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            staleTime: Infinity,
          },
        },
      });

      client.setQueryData(["pages"], { pages: mockPages } as PagesResponse);
      client.setQueryData(["schedules", "default"], {
        enabled: true,
        schedules: [],
        default_page_id: null,
      });
      client.setQueryData(["schedules", "active"], null);
      client.setQueryData(["activePage"], { page_id: null });
      client.setQueryData(["boardSettings"], {
        board_type: "black",
        boards: [],
        devices: ["flagship"],
      });

      return (
        <QueryClientProvider client={client}>
          <div className="max-w-4xl">
            <Story />
          </div>
        </QueryClientProvider>
      );
    },
  ],
};

export const Loading: Story = {
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

export const InDashboard = () => (
  <QueryClientProvider client={createQueryClient("page-1", true)}>
    <div className="min-h-screen bg-background p-6">
      <div className="container mx-auto max-w-6xl">
        <h1 className="text-3xl font-bold mb-6">Dashboard</h1>
        <ActivePageDisplay />
      </div>
    </div>
  </QueryClientProvider>
);

export const CollectionActive: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("collection:abc-123", false, false, mockCollections)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const CollectionActiveScheduled: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient("collection:abc-123", true, false, mockCollections)}>
        <div className="max-w-4xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};
