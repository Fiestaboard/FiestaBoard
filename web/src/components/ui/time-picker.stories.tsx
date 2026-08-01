import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import { Label } from "@fiestaboard/ui";
import { TimePicker } from "./time-picker";

const meta = {
  title: "UI/TimePicker",
  component: TimePicker,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    value: {
      control: "text",
      description: "Time value in HH:MM format",
    },
    placeholder: {
      control: "text",
      description: "Placeholder text",
    },
  },
} satisfies Meta<typeof TimePicker>;

export default meta;
type _Story = StoryObj<typeof meta>;

export const Default = () => {
  const [time, setTime] = useState("09:00");
  return (
    <div className="w-64">
      <TimePicker value={time} onChange={setTime} />
    </div>
  );
};

export const Empty = () => {
  const [time, setTime] = useState("");
  return (
    <div className="w-64">
      <TimePicker value={time} onChange={setTime} placeholder="Select time" />
    </div>
  );
};

export const WithLabel = () => {
  const [time, setTime] = useState("14:30");
  return (
    <div className="w-64 space-y-2">
      <Label>Start Time</Label>
      <TimePicker value={time} onChange={setTime} />
    </div>
  );
};

export const Evening = () => {
  const [time, setTime] = useState("20:00");
  return (
    <div className="w-64">
      <TimePicker value={time} onChange={setTime} />
    </div>
  );
};

export const Midnight = () => {
  const [time, setTime] = useState("00:00");
  return (
    <div className="w-64">
      <TimePicker value={time} onChange={setTime} />
    </div>
  );
};
