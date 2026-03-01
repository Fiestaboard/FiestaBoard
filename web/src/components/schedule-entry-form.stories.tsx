import type { Meta, StoryObj } from "@storybook/react";
import { ScheduleEntryForm } from "./schedule-entry-form";
import type { ScheduleEntry } from "@/lib/api";

const meta = {
  title: "Forms/ScheduleEntryForm",
  component: ScheduleEntryForm,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ScheduleEntryForm>;

export default meta;
type Story = StoryObj<typeof meta>;

const mockPages = [
  { id: "page-1", name: "Weather Dashboard" },
  { id: "page-2", name: "Transit Times" },
  { id: "page-3", name: "Morning Briefing" },
  { id: "page-4", name: "Evening Summary" },
];

export const CreateNew: Story = {
  args: {
    pages: mockPages,
    onSubmit: async (data) => {
      console.log("Create schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
  },
};

export const EditExisting: Story = {
  args: {
    schedule: {
      id: "sched-1",
      page_id: "page-1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "weekdays",
      enabled: true,
      created_at: "2024-01-01T00:00:00Z",
    } as ScheduleEntry,
    pages: mockPages,
    onSubmit: async (data) => {
      console.log("Update schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
    onDelete: () => console.log("Delete"),
  },
};

export const WithCustomDays: Story = {
  args: {
    schedule: {
      id: "sched-2",
      page_id: "page-2",
      start_time: "08:00",
      end_time: "10:00",
      day_pattern: "custom",
      custom_days: ["monday", "wednesday", "friday"],
      enabled: true,
      created_at: "2024-01-01T00:00:00Z",
    } as ScheduleEntry,
    pages: mockPages,
    onSubmit: async (data) => {
      console.log("Update schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
    onDelete: () => console.log("Delete"),
  },
};

export const OvernightSchedule: Story = {
  args: {
    schedule: {
      id: "sched-3",
      page_id: "page-3",
      start_time: "23:00",
      end_time: "06:00",
      day_pattern: "all",
      enabled: true,
      created_at: "2024-01-01T00:00:00Z",
    } as ScheduleEntry,
    pages: mockPages,
    onSubmit: async (data) => {
      console.log("Update schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
    onDelete: () => console.log("Delete"),
  },
};

export const DisabledSchedule: Story = {
  args: {
    schedule: {
      id: "sched-4",
      page_id: "page-4",
      start_time: "12:00",
      end_time: "13:00",
      day_pattern: "weekdays",
      enabled: false,
      created_at: "2024-01-01T00:00:00Z",
    } as ScheduleEntry,
    pages: mockPages,
    onSubmit: async (data) => {
      console.log("Update schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
    onDelete: () => console.log("Delete"),
  },
};

export const WithPrefill: Story = {
  args: {
    pages: mockPages,
    prefillStartTime: "14:00",
    prefillEndTime: "15:00",
    prefillDayPattern: "custom",
    prefillCustomDays: ["tuesday", "thursday"],
    onSubmit: async (data) => {
      console.log("Create schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
  },
};

export const ManyPages: Story = {
  args: {
    pages: Array.from({ length: 20 }, (_, i) => ({
      id: `page-${i + 1}`,
      name: `Page ${i + 1}`,
    })),
    onSubmit: async (data) => {
      console.log("Create schedule:", data);
      await new Promise(resolve => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
  },
};
