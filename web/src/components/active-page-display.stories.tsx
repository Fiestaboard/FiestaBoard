import type { Meta, StoryObj } from "@storybook/react";
import { ActivePageDisplay } from "./active-page-display";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Page, PagesResponse, PagePreviewResponse, SilenceStatus } from "@/lib/api";

const meta = {
  title: "Layout/ActivePageDisplay",
  component: ActivePageDisplay,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ActivePageDisplay>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Weather Dashboard",
    device_type: "flagship",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Transit Times",
    device_type: "flagship",
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-02T00:00:00Z",
  },
];

const mockPreview: PagePreviewResponse = {
  available: true,
  message: "{63}WEATHER{/63}\n{64}72°F SUNNY{/64}\n \nHIGH: 75°F\nLOW: 65°F\nHUMIDITY: 60%",
};

const createQueryClient = (
  activePageId: string | null,
  scheduleEnabled: boolean = false,
  silenceActive: boolean = false
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
  client.setQueryData(["active-page"], { page_id: activePageId });
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
    client.setQueryData(["pagePreview", activePageId], mockPreview);
  }
  
  client.setQueryData(["silenceStatus"], {
    active: silenceActive,
    until: silenceActive ? "2024-01-01T08:00:00Z" : null,
  } as SilenceStatus);
  
  client.setQueryData(["board-settings"], {
    board_color: "black",
    devices: ["flagship"],
  });
  
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
      client.setQueryData(["active-page"], { page_id: null });
      client.setQueryData(["board-settings"], {
        board_color: "black",
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
