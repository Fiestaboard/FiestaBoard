import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { BoardInstance, BoardSettings } from "@/lib/api";

import { DisplaySettings } from "./display-settings";

const flagshipBoard: BoardInstance = {
  id: "board-1",
  name: "Living Room",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "192.168.1.100",
  local_api_key: "***",
  cloud_key: "",
};

const noteBoard: BoardInstance = {
  id: "board-2",
  name: "Kitchen Note",
  device_type: "note",
  board_color: "white",
  enabled: true,
  api_mode: "cloud",
  host: "",
  local_api_key: "",
  cloud_key: "***",
};

const disabledBoard: BoardInstance = {
  id: "board-3",
  name: "Office Board",
  device_type: "flagship",
  board_color: "black",
  enabled: false,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
};

const createQueryClient = (boards: BoardInstance[]) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });

  const devices = [...new Set(boards.map((b) => b.device_type))];
  const settings: BoardSettings = {
    board_type: boards[0]?.board_color ?? "black",
    boards,
    devices,
  };

  client.setQueryData(["boardSettings"], settings);

  return client;
};

const meta = {
  title: "Settings/DisplaySettings",
  component: DisplaySettings,
  parameters: {
    layout: "padded",
    nextjs: {
      appDirectory: true,
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof DisplaySettings>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SingleBoard: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient([flagshipBoard])}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const MultipleBoards: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={createQueryClient([flagshipBoard, noteBoard, disabledBoard])}>
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const UnconfiguredBoard: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient([{ ...flagshipBoard, host: "", local_api_key: "", name: "New Board" }])}
      >
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

export const WhiteBoard: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient([{ ...flagshipBoard, board_color: "white", name: "White Flagship" }])}
      >
        <div className="max-w-lg">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
};
