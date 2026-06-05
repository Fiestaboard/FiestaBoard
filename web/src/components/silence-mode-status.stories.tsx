import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { GeneralConfig, SilenceStatus } from "@/lib/api";

import { SilenceModeStatus, SilenceModeStatusCompact } from "./silence-mode-status";

const meta = {
  title: "Layout/SilenceModeStatus",
  component: SilenceModeStatus,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    showDetails: {
      control: "boolean",
      description: "Show detailed time information",
    },
  },
} satisfies Meta<typeof SilenceModeStatus>;

export default meta;
type Story = StoryObj<typeof meta>;

const createQueryClient = (
  enabled: boolean,
  active: boolean,
  startTime: string = "23:00",
  endTime: string = "07:00",
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });

  client.setQueryData(["generalConfig"], {
    timezone: "America/Los_Angeles",
  } as GeneralConfig);

  const now = new Date();
  const nextChange = new Date(now);
  nextChange.setHours(active ? 7 : 23, 0, 0, 0);
  if (nextChange < now) {
    nextChange.setDate(nextChange.getDate() + 1);
  }

  client.setQueryData(["silenceStatus"], {
    enabled,
    active,
    start_time_utc: startTime,
    end_time_utc: endTime,
    next_change_utc: nextChange.toISOString(),
  } as SilenceStatus);

  return client;
};

export const Active: Story = {
  args: {
    showDetails: true,
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(true, true)}>
        <div className="max-w-md">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Inactive: Story = {
  args: {
    showDetails: true,
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(true, false)}>
        <div className="max-w-md">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Disabled: Story = {
  args: {
    showDetails: true,
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(false, false)}>
        <div className="max-w-md">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const WithoutDetails: Story = {
  args: {
    showDetails: false,
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(true, true)}>
        <div className="max-w-md">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Loading: Story = {
  args: {
    showDetails: true,
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <div className="max-w-md">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const CompactActive = () => (
  <QueryClientProvider client={createQueryClient(true, true)}>
    <div className="flex items-center gap-2 p-4 border rounded-lg">
      <span className="text-sm font-medium">Status:</span>
      <SilenceModeStatusCompact />
    </div>
  </QueryClientProvider>
);

export const CompactInactive = () => (
  <QueryClientProvider client={createQueryClient(true, false)}>
    <div className="flex items-center gap-2 p-4 border rounded-lg">
      <span className="text-sm font-medium">Status:</span>
      <SilenceModeStatusCompact />
    </div>
  </QueryClientProvider>
);

export const AllStates = () => (
  <div className="space-y-4 max-w-md">
    <QueryClientProvider client={createQueryClient(true, true)}>
      <div>
        <h3 className="text-sm font-semibold mb-2">Active (notifications suppressed)</h3>
        <SilenceModeStatus showDetails={true} />
      </div>
    </QueryClientProvider>

    <QueryClientProvider client={createQueryClient(true, false)}>
      <div>
        <h3 className="text-sm font-semibold mb-2">Inactive (notifications enabled)</h3>
        <SilenceModeStatus showDetails={true} />
      </div>
    </QueryClientProvider>

    <QueryClientProvider client={createQueryClient(false, false)}>
      <div>
        <h3 className="text-sm font-semibold mb-2">Disabled (feature off)</h3>
        <SilenceModeStatus showDetails={true} />
      </div>
    </QueryClientProvider>
  </div>
);
