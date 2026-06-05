import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AllSettingsResponse } from "@/lib/api";

import { GeneralSettings } from "./general-settings";

const mockAllSettings: AllSettingsResponse = {
  general: {
    timezone: "America/New_York",
    refresh_interval_seconds: 60,
    output_target: "both",
  },
  silence_schedule: {
    config: {
      enabled: true,
      start_time: "01:00",
      end_time: "12:00",
    },
  },
  polling: {
    interval_seconds: 60,
  },
  transitions: {
    strategy: "none",
    step_interval_ms: 500,
    step_size: 1,
  },
  output: {
    target: "both",
    effective_target: "both",
    available_targets: ["ui", "board", "both"],
  },
  board: {
    board_type: "black",
    boards: [
      {
        id: "board-1",
        name: "Living Room",
        device_type: "flagship",
        board_color: "black",
        enabled: true,
        api_mode: "local",
        host: "192.168.1.100",
        local_api_key: "***",
        cloud_key: "",
      },
    ],
    devices: ["flagship"],
  },
  mqtt: {
    enabled: false,
    broker_host: "localhost",
    broker_port: 1883,
    username: "",
    password: "",
    external_url: "",
  },
  status: {
    running: true,
  },
};

const createQueryClient = (overrides?: Partial<AllSettingsResponse>) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });

  const settings = { ...mockAllSettings, ...overrides };
  client.setQueryData(["all-settings"], settings);
  client.setQueryData(["status"], {
    running: settings.status.running,
    initialized: true,
    config_summary: {},
  });

  return client;
};

const meta = {
  title: "Settings/GeneralSettings",
  component: GeneralSettings,
  parameters: {
    layout: "padded",
    nextjs: {
      appDirectory: true,
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof GeneralSettings>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient()}>
        <div className="max-w-2xl">
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
        <div className="max-w-2xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const ServiceStopped: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient({
          status: { running: false },
        })}
      >
        <div className="max-w-2xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const SilenceDisabled: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient({
          silence_schedule: {
            config: {
              enabled: false,
              start_time: "01:00",
              end_time: "12:00",
            },
          },
        })}
      >
        <div className="max-w-2xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};
