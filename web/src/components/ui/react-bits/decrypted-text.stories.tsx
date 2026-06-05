import type { Meta, StoryObj } from "@storybook/react";

import DecryptedText from "./decrypted-text";

const meta = {
  title: "UI/React Bits/DecryptedText",
  component: DecryptedText,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    text: {
      control: "text",
      description: "Text to decrypt/animate",
    },
    speed: {
      control: { type: "number", min: 10, max: 200, step: 10 },
      description: "Animation speed in milliseconds per frame",
    },
    maxIterations: {
      control: { type: "number", min: 5, max: 30, step: 1 },
      description: "Number of scramble iterations",
    },
    sequential: {
      control: "boolean",
      description: "Reveal characters sequentially instead of all at once",
    },
    revealDirection: {
      control: "select",
      options: ["start", "end", "center"],
      description: "Direction to reveal characters when sequential",
    },
    animateOn: {
      control: "select",
      options: ["view", "hover", "both"],
      description: "When to trigger the animation",
    },
  },
} satisfies Meta<typeof DecryptedText>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    text: "Hover to decrypt",
    speed: 50,
    maxIterations: 10,
    animateOn: "hover",
  },
};

export const AnimateOnView: Story = {
  args: {
    text: "Animates on scroll into view",
    speed: 50,
    maxIterations: 10,
    animateOn: "view",
  },
};

export const Sequential: Story = {
  args: {
    text: "Letter by letter reveal",
    speed: 50,
    sequential: true,
    revealDirection: "start",
    animateOn: "hover",
  },
};

export const SequentialFromEnd: Story = {
  args: {
    text: "Reveals from the end",
    speed: 50,
    sequential: true,
    revealDirection: "end",
    animateOn: "hover",
  },
};

export const SequentialFromCenter: Story = {
  args: {
    text: "Reveals from the center outward",
    speed: 50,
    sequential: true,
    revealDirection: "center",
    animateOn: "hover",
  },
};

export const FastDecryption: Story = {
  args: {
    text: "Quick decrypt effect",
    speed: 20,
    maxIterations: 5,
    animateOn: "hover",
  },
};

export const SlowDecryption: Story = {
  args: {
    text: "Slow methodical decrypt",
    speed: 100,
    maxIterations: 20,
    animateOn: "hover",
  },
};

export const LargeHeadline: Story = {
  args: {
    text: "WELCOME",
    speed: 50,
    sequential: true,
    revealDirection: "start",
    animateOn: "hover",
    className: "text-6xl font-bold",
  },
};

export const InteractiveDemo = () => (
  <div className="space-y-8 text-center p-8">
    <div>
      <h3 className="text-sm text-muted-foreground mb-2">Hover to decrypt</h3>
      <DecryptedText
        text="Secret Message"
        speed={50}
        maxIterations={10}
        animateOn="hover"
        className="text-3xl font-bold"
      />
    </div>
    <div>
      <h3 className="text-sm text-muted-foreground mb-2">Sequential reveal (hover)</h3>
      <DecryptedText
        text="Decrypting data..."
        speed={50}
        sequential={true}
        revealDirection="start"
        animateOn="hover"
        className="text-2xl font-mono text-primary"
      />
    </div>
    <div>
      <h3 className="text-sm text-muted-foreground mb-2">Animates on view</h3>
      <DecryptedText
        text="Automatically revealed"
        speed={50}
        sequential={true}
        animateOn="view"
        className="text-xl font-semibold"
      />
    </div>
  </div>
);
