import { Flex, Switch, Text } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Radio } from "lucide-react";
import { fn } from "storybook/test";

import { LiveOutputSilenceStrip } from "./live-output-silence-strip";

/**
 * The page editor's Live Output row during silence (#1943), shown under the
 * real control row so the strip is reviewed where it lives.
 */
const meta = {
  title: "Silence/LiveOutputSilence",
  component: LiveOutputSilenceStrip,
  parameters: { layout: "padded" },
  args: {
    liveOutputEnabled: true,
    lastSilenced: true,
    silenceActive: true,
    overriding: false,
    until: "7:00 AM",
    onSendAnyway: fn(),
    onStopOverriding: fn(),
  },
  decorators: [
    (Story, context) => (
      <div className="max-w-xl">
        <Flex align="center" justify="between" gap="3" className="mt-3 rounded-lg border px-3 py-2">
          <Flex align="center" gap="2">
            <Switch id="live-output-toggle" checked={context.args.liveOutputEnabled} aria-label="Live Output" />
            <label htmlFor="live-output-toggle" className="flex items-center gap-1.5 text-xs sm:text-sm font-medium">
              <Radio className="h-3.5 w-3.5 text-destructive" />
              <Text as="span" size="sm">
                Live Output
              </Text>
            </label>
          </Flex>
        </Flex>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof LiveOutputSilenceStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Live Output is on and the last render came back silenced. */
export const SilencedPreviewOnly: Story = {};

export const SilencedPreviewOnlyPhone: Story = {
  globals: { viewport: { value: "phone375", isRotated: false } },
};

/** "Send to board anyway" chosen: live renders wake the board. */
export const SilencedOverriding: Story = {
  args: { overriding: true },
};

/** Live Output off: no strip, and the override is gone. */
export const LiveOutputOff: Story = {
  args: { liveOutputEnabled: false, overriding: false },
};
