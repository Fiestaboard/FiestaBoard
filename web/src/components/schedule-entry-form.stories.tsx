import type { Meta, StoryObj } from "@storybook/react";

import type { Carousel, ScheduleEntry } from "@/lib/api";

import { ScheduleEntryForm } from "./schedule-entry-form";

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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
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
      await new Promise((resolve) => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
  },
};

const mockCollections: Collection[] = [
  {
    id: "collection:abc-123",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2", "page-3"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    created_at: "2024-02-01T00:00:00Z",
  },
  {
    id: "collection:def-456",
    name: "Evening Loop",
    page_ids: ["page-3", "page-4"],
    selection_mode: "time",
    time: { interval_seconds: 60 },
    variable: null,
    created_at: "2024-02-02T00:00:00Z",
  },
];

export const WithCollections: Story = {
  args: {
    pages: mockPages,
    collections: mockCollections,
    onSubmit: async (data) => {
      console.log("Create schedule:", data);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
  },
};

export const EditCollectionEntry: Story = {
  args: {
    schedule: {
      id: "sched-5",
      page_id: "collection:abc-123",
      start_time: "07:00",
      end_time: "09:00",
      day_pattern: "weekdays",
      enabled: true,
      created_at: "2024-01-01T00:00:00Z",
    } as ScheduleEntry,
    pages: mockPages,
    collections: mockCollections,
    onSubmit: async (data) => {
      console.log("Update schedule:", data);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    },
    onCancel: () => console.log("Cancel"),
    onDelete: () => console.log("Delete"),
  },
};
