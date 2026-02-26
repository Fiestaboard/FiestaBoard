import type { Meta, StoryObj } from "@storybook/react";
import { DaySelector } from "./day-selector";
import { useState } from "react";
import type { DayPattern } from "@/lib/api";

const meta = {
  title: "Forms/DaySelector",
  component: DaySelector,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    value: {
      control: "select",
      options: ["all", "weekdays", "weekends", "custom"],
      description: "Selected day pattern",
    },
  },
} satisfies Meta<typeof DaySelector>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllDays: Story = {
  args: {
    value: "all",
    onChange: (pattern: DayPattern, customDays?: string[]) => {
      console.log("Pattern:", pattern, "Custom days:", customDays);
    },
  },
};

export const Weekdays: Story = {
  args: {
    value: "weekdays",
    onChange: (pattern: DayPattern, customDays?: string[]) => {
      console.log("Pattern:", pattern, "Custom days:", customDays);
    },
  },
};

export const Weekends: Story = {
  args: {
    value: "weekends",
    onChange: (pattern: DayPattern, customDays?: string[]) => {
      console.log("Pattern:", pattern, "Custom days:", customDays);
    },
  },
};

export const CustomSelection: Story = {
  args: {
    value: "custom",
    customDays: ["monday", "wednesday", "friday"],
    onChange: (pattern: DayPattern, customDays?: string[]) => {
      console.log("Pattern:", pattern, "Custom days:", customDays);
    },
  },
};

export const CustomAllSelected: Story = {
  args: {
    value: "custom",
    customDays: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    onChange: (pattern: DayPattern, customDays?: string[]) => {
      console.log("Pattern:", pattern, "Custom days:", customDays);
    },
  },
};

export const Interactive = () => {
  const [pattern, setPattern] = useState<DayPattern>("all");
  const [customDays, setCustomDays] = useState<string[]>([]);

  return (
    <div className="max-w-2xl space-y-4">
      <div className="text-sm text-muted-foreground">
        <strong>Selected:</strong> {pattern}
        {pattern === "custom" && ` (${customDays.length} days)`}
      </div>
      <DaySelector
        value={pattern}
        customDays={customDays}
        onChange={(newPattern, newCustomDays) => {
          setPattern(newPattern);
          setCustomDays(newCustomDays || []);
        }}
      />
      {pattern === "custom" && (
        <div className="text-xs text-muted-foreground">
          Selected days: {customDays.join(", ") || "none"}
        </div>
      )}
    </div>
  );
};

export const InForm = () => {
  const [pattern, setPattern] = useState<DayPattern>("weekdays");
  const [customDays, setCustomDays] = useState<string[]>([]);

  return (
    <div className="max-w-2xl space-y-6 border rounded-lg p-6">
      <div>
        <h3 className="text-lg font-semibold mb-2">Schedule Settings</h3>
        <p className="text-sm text-muted-foreground">
          Configure when this schedule should be active
        </p>
      </div>
      
      <DaySelector
        value={pattern}
        customDays={customDays}
        onChange={(newPattern, newCustomDays) => {
          setPattern(newPattern);
          setCustomDays(newCustomDays || []);
        }}
      />
      
      <div className="flex gap-2 pt-4 border-t">
        <button className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium">
          Save Schedule
        </button>
        <button className="px-4 py-2 rounded-md border text-sm font-medium">
          Cancel
        </button>
      </div>
    </div>
  );
};
