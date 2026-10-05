import { PageCard } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import firstPartyOutputs from "@/__tests__/mocks/first-party-outputs.json";
import type { BoardInstance, BoardSettings } from "@/lib/api";

import { DisplaySettings } from "./display-settings";
import { OUTPUTS_QUERY_KEY } from "./output-boards";

/** A Vestaboard's connection: its `output_config`, which the screen edits (the flat fields are the read-back view). */
function vestaboard(config: Record<string, unknown>): Pick<BoardInstance, "output" | "output_config"> {
  return { output: "vestaboard", output_config: config };
}

const flagshipBoard: BoardInstance = {
  id: "board-1",
  name: "Living Room",
  device_type: "flagship",
  board_color: "black",
  // A Flagship built before 2026: its code-62 flap is a degree sign (#1657).
  code62_glyph: "degree",
  enabled: true,
  api_mode: "local",
  host: "192.168.1.100",
  local_api_key: "***",
  cloud_key: "",
  ...vestaboard({ api_mode: "local", host: "192.168.1.100", port: 7000, local_api_key: "***" }),
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
  ...vestaboard({ api_mode: "cloud", cloud_key: "***" }),
};

const disabledBoard: BoardInstance = {
  id: "board-3",
  name: "Office Board",
  device_type: "flagship",
  board_color: "black",
  // A Flagship built from 2026: the same flap carries a heart (#1657).
  code62_glyph: "heart",
  enabled: false,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
  ...vestaboard({ api_mode: "local" }),
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
  client.setQueryData(OUTPUTS_QUERY_KEY, firstPartyOutputs);

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
          {/* PageSection pads and divides itself but draws no surface — the
              page card is what a settings section lives in, so the story
              shows it in one rather than floating unpadded. */}
          <PageCard>
            <Story />
          </PageCard>
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
          {/* PageSection pads and divides itself but draws no surface — the
              page card is what a settings section lives in, so the story
              shows it in one rather than floating unpadded. */}
          <PageCard>
            <Story />
          </PageCard>
        </div>
      </QueryClientProvider>
    ),
  ],
};

export const UnconfiguredBoard: Story = {
  decorators: [
    (Story) => (
      <QueryClientProvider
        client={createQueryClient([
          { ...flagshipBoard, host: "", local_api_key: "", name: "New Board", ...vestaboard({ api_mode: "local" }) },
        ])}
      >
        <div className="max-w-lg">
          {/* PageSection pads and divides itself but draws no surface — the
              page card is what a settings section lives in, so the story
              shows it in one rather than floating unpadded. */}
          <PageCard>
            <Story />
          </PageCard>
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
          {/* PageSection pads and divides itself but draws no surface — the
              page card is what a settings section lives in, so the story
              shows it in one rather than floating unpadded. */}
          <PageCard>
            <Story />
          </PageCard>
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
          {/* PageSection pads and divides itself but draws no surface — the
              page card is what a settings section lives in, so the story
              shows it in one rather than floating unpadded. */}
          <PageCard>
            <Story />
          </PageCard>
        </div>
      </QueryClientProvider>
    ),
  ],
};
