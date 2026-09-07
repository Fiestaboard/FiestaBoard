import { PageCard } from "@fiestaboard/ui";
import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AllSettingsResponse, DisplaySettings } from "@/lib/api";

import { AnimationSettings } from "./animation-settings";

const baseDisplay: DisplaySettings = {
  reduce_motion: false,
  board_animations: "on",
  site_animations: "on",
  board_flap_speed: "standard",
};

/**
 * Seed the cache directly rather than mocking fetch: the card reads a single
 * `all-settings` query, and the a11y run should exercise the rendered controls
 * rather than a loading skeleton.
 */
const createQueryClient = (display: DisplaySettings) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["all-settings"], { display } as unknown as AllSettingsResponse);
  return client;
};

const withSettings = (display: DisplaySettings) => [
  (Story: React.ComponentType) => (
    <QueryClientProvider client={createQueryClient(display)}>
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
];

const meta = {
  title: "Settings/AnimationSettings",
  component: AnimationSettings,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof AnimationSettings>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Defaults: board animations on, the shipped 80ms `standard` cadence. */
export const Default: Story = {
  decorators: withSettings(baseDisplay),
};

export const RelaxedFlapSpeed: Story = {
  decorators: withSettings({ ...baseDisplay, board_flap_speed: "relaxed" }),
};

/** The hardware cadence — offered, but deliberately not the default. */
export const HardwareFlapSpeed: Story = {
  decorators: withSettings({ ...baseDisplay, board_flap_speed: "hardware" }),
};

/** With the board kill switch off, the preview is replaced by an explanation. */
export const BoardAnimationsOff: Story = {
  decorators: withSettings({ ...baseDisplay, board_animations: "off" }),
};

/** `reduce_motion` overrides everything, flip speed included. */
export const ReduceMotion: Story = {
  decorators: withSettings({ ...baseDisplay, reduce_motion: true }),
};
