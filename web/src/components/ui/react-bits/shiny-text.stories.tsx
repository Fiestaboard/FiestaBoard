import type { Meta, StoryObj } from "@storybook/react";
import ShinyText from "./shiny-text";

const meta = {
  title: "UI/React Bits/ShinyText",
  component: ShinyText,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    text: {
      control: "text",
      description: "Text to display with shiny effect",
    },
    disabled: {
      control: "boolean",
      description: "Disable the animation",
    },
    speed: {
      control: { type: "number", min: 1, max: 10, step: 0.5 },
      description: "Animation speed in seconds",
    },
    className: {
      control: "text",
      description: "Additional CSS classes",
    },
  },
} satisfies Meta<typeof ShinyText>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    text: "Configured",
    speed: 3,
  },
};

export const Fast: Story = {
  args: {
    text: "Fast Animation",
    speed: 1,
  },
};

export const Slow: Story = {
  args: {
    text: "Slow Animation",
    speed: 8,
  },
};

export const Disabled: Story = {
  args: {
    text: "Static Text",
    disabled: true,
  },
};

export const LargeText: Story = {
  args: {
    text: "Large Shiny Text",
    speed: 3,
    className: "text-4xl font-bold",
  },
};

export const ColoredText: Story = {
  args: {
    text: "Colored Shiny Text",
    speed: 3,
    className: "text-2xl font-bold text-primary",
  },
};

export const InBadge = () => (
  <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/20 bg-primary/5">
    <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
    <ShinyText text="Configured" speed={4} className="text-sm font-medium" />
  </div>
);

export const MultipleTexts = () => (
  <div className="space-y-4 text-center">
    <div className="text-3xl font-bold">
      <ShinyText text="Welcome" speed={3} />
    </div>
    <div className="text-2xl font-semibold text-primary">
      <ShinyText text="to" speed={4} />
    </div>
    <div className="text-4xl font-bold">
      <ShinyText text="FiestaBoard" speed={2} />
    </div>
  </div>
);
