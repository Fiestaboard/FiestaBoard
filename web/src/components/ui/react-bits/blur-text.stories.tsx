import type { Meta, StoryObj } from "@storybook/react";

import BlurText from "./blur-text";

const meta = {
  title: "UI/React Bits/BlurText",
  component: BlurText,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    text: {
      control: "text",
      description: "Text to animate with blur effect",
    },
    delay: {
      control: { type: "number", min: 50, max: 500, step: 50 },
      description: "Delay between each element animation in milliseconds",
    },
    animateBy: {
      control: "select",
      options: ["words", "letters"],
      description: "Animate by words or individual letters",
    },
    direction: {
      control: "select",
      options: ["top", "bottom"],
      description: "Direction of the blur animation",
    },
    stepDuration: {
      control: { type: "number", min: 0.1, max: 2, step: 0.05 },
      description: "Duration of each step animation in seconds",
    },
  },
} satisfies Meta<typeof BlurText>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    text: "Blur text animation",
    delay: 200,
    animateBy: "words",
    direction: "top",
  },
};

export const ByLetters: Story = {
  args: {
    text: "Character by character",
    delay: 50,
    animateBy: "letters",
    direction: "top",
  },
};

export const FromBottom: Story = {
  args: {
    text: "Appearing from below",
    delay: 200,
    animateBy: "words",
    direction: "bottom",
  },
};

export const FastAnimation: Story = {
  args: {
    text: "Quick blur effect",
    delay: 50,
    animateBy: "words",
    stepDuration: 0.2,
  },
};

export const SlowAnimation: Story = {
  args: {
    text: "Slow and smooth",
    delay: 300,
    animateBy: "words",
    stepDuration: 0.8,
  },
};

export const LargeHeadline: Story = {
  args: {
    text: "Welcome to FiestaBoard",
    delay: 150,
    animateBy: "words",
    className: "text-4xl font-bold",
  },
};

export const ColoredText: Story = {
  args: {
    text: "Colorful blur animation",
    delay: 200,
    animateBy: "words",
    className: "text-2xl font-semibold text-primary",
  },
};

export const MultipleLines = () => (
  <div className="space-y-4 text-center">
    <BlurText text="First line appears" delay={150} animateBy="words" className="text-2xl font-bold" />
    <BlurText text="Then the second line" delay={150} animateBy="words" className="text-xl text-muted-foreground" />
    <BlurText text="And finally the third" delay={150} animateBy="words" className="text-lg" />
  </div>
);
