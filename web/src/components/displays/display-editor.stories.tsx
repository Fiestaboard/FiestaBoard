import { PageCard } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import firstPartyOutputs from "@/__tests__/mocks/first-party-outputs.json";
import { OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import type { BoardInstance, BoardSettings } from "@/lib/api";

import { DisplayEditor } from "./display-editor";

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

/**
 * PageSection pads and divides itself but draws no surface — the page card
 * is what a display's settings live in, so a story shows it in one.
 */
function inCard(client: QueryClient) {
  return function Decorator(Story: () => ReactNode) {
    return (
      <QueryClientProvider client={client}>
        <div className="max-w-lg">
          <PageCard>
            <Story />
          </PageCard>
        </div>
      </QueryClientProvider>
    );
  };
}

const meta = {
  title: "Displays/DisplayEditor",
  component: DisplayEditor,
  parameters: {
    layout: "padded",
  },
  args: { boardId: "board-1" },
  tags: ["autodocs"],
} satisfies Meta<typeof DisplayEditor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LocalFlagship: Story = {
  decorators: [inCard(createQueryClient([flagshipBoard, noteBoard]))],
};

export const CloudNote: Story = {
  args: { boardId: "board-2" },
  decorators: [inCard(createQueryClient([flagshipBoard, noteBoard]))],
};

export const UnconfiguredBoard: Story = {
  decorators: [
    inCard(
      createQueryClient([
        { ...flagshipBoard, host: "", local_api_key: "", name: "New Board", ...vestaboard({ api_mode: "local" }) },
      ]),
    ),
  ],
};

export const Loading: Story = {
  decorators: [inCard(new QueryClient())],
};

export const WhiteBoard: Story = {
  decorators: [inCard(createQueryClient([{ ...flagshipBoard, board_color: "white", name: "White Flagship" }]))],
};
