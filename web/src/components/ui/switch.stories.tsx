import type { Meta, StoryObj } from "@storybook/react";
import { Switch } from "./switch";
import { Label } from "./label";

const meta = {
  title: "UI/Switch",
  component: Switch,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    checked: {
      control: "boolean",
      description: "Controlled checked state",
    },
    disabled: {
      control: "boolean",
      description: "Disabled state",
    },
  },
} satisfies Meta<typeof Switch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    "aria-label": "Toggle setting",
  },
};

export const Checked: Story = {
  args: {
    defaultChecked: true,
    "aria-label": "Toggle setting",
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
    "aria-label": "Toggle setting",
  },
};

export const DisabledChecked: Story = {
  args: {
    disabled: true,
    defaultChecked: true,
    "aria-label": "Toggle setting",
  },
};

export const WithLabel = () => (
  <div className="flex items-center space-x-2">
    <Switch id="airplane-mode" />
    <Label htmlFor="airplane-mode">Airplane Mode</Label>
  </div>
);

export const FormExample = () => (
  <div className="space-y-4">
    <div className="flex items-center justify-between w-64">
      <Label htmlFor="notifications">Notifications</Label>
      <Switch id="notifications" defaultChecked />
    </div>
    <div className="flex items-center justify-between w-64">
      <Label htmlFor="marketing">Marketing emails</Label>
      <Switch id="marketing" />
    </div>
    <div className="flex items-center justify-between w-64">
      <Label htmlFor="security">Security alerts</Label>
      <Switch id="security" defaultChecked />
    </div>
  </div>
);

export const AllStates = () => (
  <div className="space-y-6">
    <div>
      <h3 className="text-sm font-medium mb-3">Interactive States</h3>
      <div className="flex flex-wrap gap-6">
        <div className="flex items-center gap-2">
          <Switch id="unchecked" />
          <Label htmlFor="unchecked">Unchecked</Label>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="checked" defaultChecked />
          <Label htmlFor="checked">Checked</Label>
        </div>
      </div>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">Disabled States</h3>
      <div className="flex flex-wrap gap-6">
        <div className="flex items-center gap-2">
          <Switch id="disabled-unchecked" disabled />
          <Label htmlFor="disabled-unchecked">Disabled Unchecked</Label>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="disabled-checked" disabled defaultChecked />
          <Label htmlFor="disabled-checked">Disabled Checked</Label>
        </div>
      </div>
    </div>
  </div>
);
