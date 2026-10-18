import { Button } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor, within } from "storybook/test";

import { SilenceNotice } from "./silence-notice";

/**
 * The one way the app says "this board is silenced" (#1943). Each surface
 * passes its own sentence; the title, icon and layout never change.
 */
const meta = {
  title: "Silence/SilenceNotice",
  component: SilenceNotice,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
  args: {
    until: "7:00 AM",
    description: "“Weather” will show when silence ends. The board stays quiet until then.",
  },
  decorators: [
    (Story) => (
      <div className="max-w-3xl">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SilenceNotice>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Not silenced: renders nothing. */
export const Hidden: Story = {
  args: { active: false },
};

export const InfoDefault: Story = {};

export const InfoWithActions: Story = {
  args: {
    description: (
      <>
        <span className="block">“Weather” will show when silence ends. The board stays quiet until then.</span>
        <span className="mt-1 block">Held message: “GOOD MORNING EVERYONE HAVE A…” — it shows first.</span>
      </>
    ),
    children: (
      <>
        <Button variant="outline" size="sm">
          Show now
        </Button>
        <Button variant="ghost" size="sm">
          Discard message
        </Button>
      </>
    ),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => expect(canvas.getByRole("button", { name: "Show now" })).toBeVisible());
    await waitFor(() => expect(canvas.getByRole("button", { name: "Discard message" })).toBeVisible());
  },
};

/** The end of the window is unknown (an older API that reports neither field). */
export const NoTime: Story = {
  args: { until: null },
};

/** Force Set: the action in front of you wakes the board. */
export const Warning: Story = {
  args: {
    variant: "warning",
    description: "Force Set shows this page right away and wakes the board.",
  },
};

/** The page builder's Live Output strip: one line, extra-small, one action. */
export const Compact: Story = {
  args: {
    compact: true,
    description: "Live Output is previewing only. The board stays quiet.",
    children: (
      <Button variant="outline" size="sm">
        Send to board anyway
      </Button>
    ),
  },
};

/** 375 px: the actions wrap into a full-width row under the text, 44 px tall. */
export const Phone: Story = {
  ...InfoWithActions,
  globals: { viewport: { value: "phone375", isRotated: false } },
};
