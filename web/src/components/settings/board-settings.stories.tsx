import type { Meta, StoryObj } from "@storybook/react";
import { BoardSettings } from "./board-settings";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { BoardConfig } from "@/lib/api";

const mockLocalConfig: BoardConfig = {
  api_mode: "local",
  local_api_key: "***",
  cloud_key: "",
  host: "192.168.1.100",
  transition_strategy: null,
  transition_interval_ms: null,
  transition_step_size: null,
};

const mockCloudConfig: BoardConfig = {
  api_mode: "cloud",
  local_api_key: "",
  cloud_key: "***",
  host: "",
  transition_strategy: null,
  transition_interval_ms: null,
  transition_step_size: null,
};

const mockUnconfigured: BoardConfig = {
  api_mode: "local",
  local_api_key: "",
  cloud_key: "",
  host: "",
  transition_strategy: null,
  transition_interval_ms: null,
  transition_step_size: null,
};

const createQueryClient = (config: BoardConfig) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });

  client.setQueryData(["board-config"], {
    config,
    api_modes: ["local", "cloud"],
  });

  return client;
};

const meta = {
  title: "Settings/BoardSettings",
  component: BoardSettings,
  parameters: {
    layout: "padded",
    nextjs: {
      appDirectory: true,
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof BoardSettings>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LocalApi: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(mockLocalConfig)}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const CloudApi: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(mockCloudConfig)}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Unconfigured: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient(mockUnconfigured)}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const Loading: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={new QueryClient()}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};
