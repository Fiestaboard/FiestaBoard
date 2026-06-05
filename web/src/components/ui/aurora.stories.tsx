import type { Meta, StoryObj } from "@storybook/react";

import { Aurora } from "./aurora";

const meta = {
  title: "UI/Aurora",
  component: Aurora,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  argTypes: {
    colorStops: {
      control: "object",
      description: "Array of three color hex values for gradient",
    },
    amplitude: {
      control: { type: "number", min: 0, max: 3, step: 0.1 },
      description: "Wave amplitude (height)",
    },
    blend: {
      control: { type: "number", min: 0, max: 1, step: 0.1 },
      description: "Blend factor for aurora effect",
    },
    speed: {
      control: { type: "number", min: 0.1, max: 5, step: 0.1 },
      description: "Animation speed multiplier",
    },
  },
} satisfies Meta<typeof Aurora>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Aurora Background</h1>
          <p className="text-xl text-white/80">WebGL-powered animated gradient</p>
        </div>
      </div>
    </div>
  ),
};

export const CustomColors: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora colorStops={["#ff0080", "#7928ca", "#ff0080"]} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Pink & Purple</h1>
          <p className="text-xl text-white/80">Custom color gradient</p>
        </div>
      </div>
    </div>
  ),
};

export const GreenTheme: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-gray-900">
      <Aurora colorStops={["#10b981", "#34d399", "#10b981"]} amplitude={1.5} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Emerald Aurora</h1>
          <p className="text-xl text-white/80">Soothing green waves</p>
        </div>
      </div>
    </div>
  ),
};

export const HighAmplitude: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora amplitude={2.5} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">High Waves</h1>
          <p className="text-xl text-white/80">Increased amplitude for dramatic effect</p>
        </div>
      </div>
    </div>
  ),
};

export const LowAmplitude: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora amplitude={0.3} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Subtle Waves</h1>
          <p className="text-xl text-white/80">Low amplitude for gentle effect</p>
        </div>
      </div>
    </div>
  ),
};

export const FastAnimation: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora speed={3} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Fast Motion</h1>
          <p className="text-xl text-white/80">3x speed multiplier</p>
        </div>
      </div>
    </div>
  ),
};

export const SlowAnimation: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-black">
      <Aurora speed={0.3} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Slow Motion</h1>
          <p className="text-xl text-white/80">0.3x speed for calm effect</p>
        </div>
      </div>
    </div>
  ),
};

export const FireTheme: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-red-950">
      <Aurora colorStops={["#dc2626", "#f97316", "#dc2626"]} amplitude={1.8} speed={2} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Fire Aurora</h1>
          <p className="text-xl text-white/80">Red & orange flames</p>
        </div>
      </div>
    </div>
  ),
};

export const OceanTheme: Story = {
  render: () => (
    <div className="relative h-screen w-full bg-blue-950">
      <Aurora colorStops={["#0ea5e9", "#06b6d4", "#0ea5e9"]} amplitude={1.2} speed={0.8} blend={0.6} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-white">
          <h1 className="text-6xl font-bold mb-4">Ocean Waves</h1>
          <p className="text-xl text-white/80">Blue cyan gradient</p>
        </div>
      </div>
    </div>
  ),
};
