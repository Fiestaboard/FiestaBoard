import { PageCard } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";

import type { BoardInstance } from "@/lib/api";

import { TileGridAssignment } from "./tile-grid-assignment";

// A 2×2 local-mode Note array with one of its four slots assigned.
const partialArray: BoardInstance = {
  id: "board-array",
  name: "Hallway Array",
  device_type: "note_array",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
  notes_wide: 2,
  notes_tall: 2,
  tiles: [{ row: 0, col: 0, host: "192.168.1.101", port: 7000, local_api_key: "***" }],
};

const meta = {
  title: "Settings/TileGridAssignment",
  component: TileGridAssignment,
  parameters: {
    layout: "padded",
  },
  args: {
    onUpdate: () => {},
  },
  decorators: [
    (Story) => (
      <div className="max-w-lg">
        <PageCard>
          <Story />
        </PageCard>
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof TileGridAssignment>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Some slots unassigned: renders the warning-colored "n/total assigned" badge. */
export const PartiallyAssigned: Story = {
  args: {
    board: partialArray,
  },
};
