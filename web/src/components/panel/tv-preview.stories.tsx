import type { Meta, StoryObj } from "@storybook/react";

import { TvPreview } from "./tv-preview";

/**
 * True-to-shape preview of a FiestaPanel on its screen: the TV outline at
 * the chosen aspect ratio with the auto-fit Note-block grid inside it at
 * real proportional coverage. Drag the diagonal control to watch the
 * auto-fit algorithm re-fit the grid (mirrors src/panels/autofit.py).
 */
const meta = {
  title: "Panel/TvPreview",
  component: TvPreview,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    diagonalInches: {
      control: { type: "range", min: 3, max: 200, step: 0.5 },
      description: "Screen diagonal in inches — drives the auto-fit grid",
    },
    aspectW: {
      control: { type: "number", min: 1, max: 100 },
      description: "Aspect ratio width (e.g. 16 in 16:9)",
    },
    aspectH: {
      control: { type: "number", min: 1, max: 100 },
      description: "Aspect ratio height (e.g. 9 in 16:9)",
    },
  },
} satisfies Meta<typeof TvPreview>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A common living-room TV: one column of four Note blocks. */
export const LivingRoom55Inch: Story = {
  args: { diagonalInches: 55, aspectW: 16, aspectH: 9 },
};

/** The same 55" diagonal declared ultrawide fits 2×3 blocks instead. */
export const Ultrawide21x9: Story = {
  args: { diagonalInches: 55, aspectW: 21, aspectH: 9 },
};

/** A big wall: 85" 16:9 fills 3×6 blocks. */
export const Wall85Inch: Story = {
  args: { diagonalInches: 85, aspectW: 16, aspectH: 9 },
};

/** Portrait signage (9:16) stacks blocks tall. */
export const PortraitSignage: Story = {
  args: { diagonalInches: 55, aspectW: 9, aspectH: 16 },
};

/** 4:3 legacy signage. */
export const Signage4x3: Story = {
  args: { diagonalInches: 40, aspectW: 4, aspectH: 3 },
};

/** The 3" floor: one block, larger than the screen — the viewer shrinks
 * it to fit, and the preview shows it filling the screen. */
export const PocketScreen3Inch: Story = {
  args: { diagonalInches: 3, aspectW: 16, aspectH: 9 },
};
