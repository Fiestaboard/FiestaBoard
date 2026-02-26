import type { Meta, StoryObj } from "@storybook/react";
import { Label } from "./label";
import { Input } from "./input";
import { Switch } from "./switch";

const meta = {
  title: "UI/Label",
  component: Label,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Label>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: "Label text",
  },
};

export const WithInput = () => (
  <div className="grid w-full max-w-sm items-center gap-1.5">
    <Label htmlFor="name">Name</Label>
    <Input type="text" id="name" placeholder="Enter your name" />
  </div>
);

export const WithSwitch = () => (
  <div className="flex items-center space-x-2">
    <Switch id="airplane-mode" />
    <Label htmlFor="airplane-mode">Airplane Mode</Label>
  </div>
);

export const Disabled = () => (
  <div className="grid w-full max-w-sm items-center gap-1.5">
    <Label htmlFor="disabled-input" className="peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
      Disabled
    </Label>
    <Input type="text" id="disabled-input" placeholder="Disabled" disabled className="peer" />
  </div>
);
