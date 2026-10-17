import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";

import { ForceSetDialog } from "./force-set-dialog";

/**
 * Force Set deliberately beats silence (#949). During silence it says so and
 * names the choice on its button (#1943); otherwise it is unchanged.
 */
const meta = {
  title: "Silence/ForceSetDialog",
  component: ForceSetDialog,
  parameters: { layout: "centered" },
  args: {
    open: true,
    onOpenChange: fn(),
    pageId: "page-2",
    pageName: "Transit Times",
  },
} satisfies Meta<typeof ForceSetDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Not silenced: today's dialog. */
export const Default: Story = {};

export const Silenced: Story = {
  args: { silencedUntil: "7:00 AM" },
  play: async () => {
    const dialog = within(document.body);
    await expect(await dialog.findByTestId("force-set-silence")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Show now anyway" })).toBeVisible();
  },
};

export const SilencedPhone: Story = {
  ...Silenced,
  globals: { viewport: { value: "phone375", isRotated: false } },
};
