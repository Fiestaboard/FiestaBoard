import type { Meta, StoryObj } from "@storybook/react";
import { TimezonePicker } from "./timezone-picker";
import { useState } from "react";
import { Label } from "./label";

const meta = {
  title: "UI/TimezonePicker",
  component: TimezonePicker,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    value: {
      control: "text",
      description: "Selected timezone value (IANA timezone name)",
    },
    disabled: {
      control: "boolean",
      description: "Disabled state",
    },
  },
} satisfies Meta<typeof TimezonePicker>;

export default meta;
type _Story = StoryObj<typeof meta>;

export const Default = () => {
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  return (
    <div className="w-80">
      <TimezonePicker value={timezone} onChange={setTimezone} />
    </div>
  );
};

export const Empty = () => {
  const [timezone, setTimezone] = useState("");
  return (
    <div className="w-80">
      <TimezonePicker value={timezone} onChange={setTimezone} />
    </div>
  );
};

export const WithLabel = () => {
  const [timezone, setTimezone] = useState("America/New_York");
  return (
    <div className="w-80 space-y-2">
      <Label>Timezone</Label>
      <TimezonePicker value={timezone} onChange={setTimezone} />
    </div>
  );
};

export const Disabled = () => {
  const [timezone, setTimezone] = useState("Europe/London");
  return (
    <div className="w-80">
      <TimezonePicker value={timezone} onChange={setTimezone} disabled />
    </div>
  );
};

export const InvalidTimezone = () => {
  const [timezone, setTimezone] = useState("Invalid/Timezone");
  return (
    <div className="w-80">
      <TimezonePicker value={timezone} onChange={setTimezone} />
    </div>
  );
};
