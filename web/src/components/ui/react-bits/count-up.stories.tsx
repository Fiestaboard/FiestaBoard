import type { Meta, StoryObj } from "@storybook/react";
import CountUp from "./count-up";

const meta = {
  title: "UI/React Bits/CountUp",
  component: CountUp,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    to: {
      control: "number",
      description: "Target number to count up to",
    },
    from: {
      control: "number",
      description: "Starting number",
    },
    duration: {
      control: { type: "number", min: 0.5, max: 10, step: 0.5 },
      description: "Animation duration in seconds",
    },
    delay: {
      control: { type: "number", min: 0, max: 5, step: 0.5 },
      description: "Delay before animation starts in seconds",
    },
    separator: {
      control: "text",
      description: "Thousands separator character",
    },
    startWhen: {
      control: "boolean",
      description: "Whether to start animation",
    },
  },
} satisfies Meta<typeof CountUp>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    to: 100,
    from: 0,
    duration: 2,
  },
};

export const WithSeparator: Story = {
  args: {
    to: 1000000,
    from: 0,
    duration: 2,
    separator: ",",
  },
};

export const Decimals: Story = {
  args: {
    to: 99.99,
    from: 0,
    duration: 2,
  },
};

export const FastAnimation: Story = {
  args: {
    to: 500,
    from: 0,
    duration: 0.5,
  },
};

export const SlowAnimation: Story = {
  args: {
    to: 50,
    from: 0,
    duration: 5,
  },
};

export const WithDelay: Story = {
  args: {
    to: 100,
    from: 0,
    duration: 2,
    delay: 2,
  },
};

export const LargeNumber: Story = {
  args: {
    to: 9876543,
    from: 0,
    duration: 3,
    separator: ",",
    className: "text-4xl font-bold text-primary",
  },
};

export const Percentage: Story = {
  render: () => (
    <div className="flex items-center gap-1 text-2xl font-semibold">
      <CountUp to={87.5} from={0} duration={2} />
      <span>%</span>
    </div>
  ),
};

export const MultipleCounters = () => (
  <div className="flex gap-8 text-center">
    <div>
      <div className="text-4xl font-bold text-primary">
        <CountUp to={1234} from={0} duration={2} separator="," />
      </div>
      <div className="text-sm text-muted-foreground mt-2">Total Users</div>
    </div>
    <div>
      <div className="text-4xl font-bold text-success">
        <CountUp to={98.7} from={0} duration={2} />
        <span>%</span>
      </div>
      <div className="text-sm text-muted-foreground mt-2">Success Rate</div>
    </div>
    <div>
      <div className="text-4xl font-bold text-info">
        <CountUp to={42} from={0} duration={2} />
      </div>
      <div className="text-sm text-muted-foreground mt-2">Active Projects</div>
    </div>
  </div>
);
